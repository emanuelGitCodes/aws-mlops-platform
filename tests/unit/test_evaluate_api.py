import json
import urllib.error
from unittest import mock

import pytest

from scripts import evaluate_api
from tests.unit.conftest import VALID
from tests.unit.conftest import signing_session as _session


def _fixture(label: int, row_id: int) -> dict:
    return {"row_id": row_id, "record": VALID, "label": label}


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("s3://bucket/prefix/api_test", ("bucket", "prefix/api_test")),
        ("s3://bucket/prefix/", ("bucket", "prefix")),
        ("s3://bucket/a/b/api_test.jsonl", ("bucket", "a/b/api_test.jsonl")),
    ],
)
def test_parse_s3_uri_splits_bucket_from_key(uri, expected):
    assert evaluate_api.parse_s3_uri(uri) == expected


@pytest.mark.parametrize(
    "uri",
    [
        "https://bucket/prefix",  # not an S3 URI at all
        "s3://bucket",  # no key
        "s3://bucket/",  # empty key
        "s3:///prefix",  # no bucket
        "",
    ],
)
def test_parse_s3_uri_rejects_malformed_input(uri):
    """Reject a malformed S3 URI before an S3 request."""
    with pytest.raises(ValueError, match="fixture S3 URI"):
        evaluate_api.parse_s3_uri(uri)


def _preprocess_page(outputs):
    return [
        {
            "PipelineExecutionSteps": [
                {"StepName": "Train", "Metadata": {}},
                {
                    "StepName": "Preprocess",
                    "Metadata": {"ProcessingJob": {"Arn": "arn:aws:sagemaker:::job/prep-1"}},
                },
            ]
        }
    ], {"ProcessingOutputConfig": {"Outputs": outputs}}


def _sagemaker_client(pages, job):
    client = mock.Mock()
    client.get_paginator.return_value.paginate.return_value = pages
    client.describe_processing_job.return_value = job
    return client


def test_resolve_fixture_s3_uri_finds_the_api_test_output():
    pages, job = _preprocess_page(
        [
            {"OutputName": "train", "S3Output": {"S3Uri": "s3://bucket/train"}},
            {"OutputName": "api_test", "S3Output": {"S3Uri": "s3://bucket/api_test"}},
        ]
    )
    client = _sagemaker_client(pages, job)
    with mock.patch.object(evaluate_api.boto3, "client", return_value=client):
        assert evaluate_api.resolve_fixture_s3_uri("arn:execution") == "s3://bucket/api_test"

    # The lookup uses the job name, not the full ARN.
    assert client.describe_processing_job.call_args.kwargs == {"ProcessingJobName": "prep-1"}


def test_resolve_fixture_s3_uri_fails_when_the_execution_has_no_api_test_output():
    """Raise an explicit error when an execution has no fixture output."""
    pages, job = _preprocess_page(
        [{"OutputName": "train", "S3Output": {"S3Uri": "s3://bucket/train"}}]
    )
    client = _sagemaker_client(pages, job)
    with mock.patch.object(evaluate_api.boto3, "client", return_value=client):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="api_test"):
            evaluate_api.resolve_fixture_s3_uri("arn:execution")


def _s3_client_returning(payload: bytes):
    client = mock.Mock()
    client.get_object.return_value = {"Body": mock.Mock(read=mock.Mock(return_value=payload))}
    return client


def test_load_fixture_reads_jsonl_and_appends_the_default_filename():
    payload = b'{"row_id": 0, "label": 1}\n\n{"row_id": 1, "label": 0}\n'
    client = _s3_client_returning(payload)
    with mock.patch.object(evaluate_api.boto3, "client", return_value=client):
        records = evaluate_api.load_fixture("s3://bucket/prefix")

    assert [record["row_id"] for record in records] == [0, 1]
    # A prefix takes the fixture filename. Blank lines are skipped.
    assert client.get_object.call_args.kwargs == {
        "Bucket": "bucket",
        "Key": "prefix/api_test.jsonl",
    }


def test_load_fixture_uses_an_explicit_jsonl_key_as_given():
    client = _s3_client_returning(b'{"row_id": 0}\n')
    with mock.patch.object(evaluate_api.boto3, "client", return_value=client):
        evaluate_api.load_fixture("s3://bucket/a/api_test.jsonl")
    assert client.get_object.call_args.kwargs["Key"] == "a/api_test.jsonl"


def test_load_fixture_rejects_an_empty_fixture():
    """Reject an empty evaluation fixture."""
    with mock.patch.object(evaluate_api.boto3, "client", return_value=_s3_client_returning(b"\n")):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="empty"):
            evaluate_api.load_fixture("s3://bucket/prefix")


def test_select_records_is_deterministic_and_class_balanced():
    records = [_fixture(index % 2, index) for index in range(20)]

    selected = evaluate_api.select_records(records, limit=6, all_records=False)

    assert selected == evaluate_api.select_records(records, limit=6, all_records=False)
    assert len(selected) == 6
    assert {record["label"] for record in selected} == {0, 1}


def test_evaluate_api_records_reports_labeled_endpoint_results():
    records = [_fixture(0, 0), _fixture(0, 1), _fixture(1, 2), _fixture(1, 3)]
    responses = [
        {"score": 0.1, "prediction": 0},
        {"score": 0.6, "prediction": 1},
        {"score": 0.5, "prediction": 1},
        {"score": 0.9, "prediction": 1},
    ]
    with mock.patch.object(evaluate_api, "invoke_prediction", side_effect=responses):
        report = evaluate_api.evaluate_api_records(
            records, "https://example.test/predict", _session()
        )

    assert report["source"] == "deployed_api"
    assert report["evaluated_record_count"] == 4
    assert report["accuracy"] == pytest.approx(0.75)
    assert report["confusion_matrix"]["false_positive"] == 1


def test_invoke_prediction_rejects_mismatched_score_and_classification():
    response = mock.MagicMock()
    response.read.return_value = json.dumps({"churn_probability": 0.7, "churn": False}).encode()
    response.__enter__.return_value = response
    with mock.patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="does not match"):
            evaluate_api.invoke_prediction("https://example.test/predict", VALID, _session())


def test_invoke_prediction_reports_http_failure():
    error = urllib.error.HTTPError("https://example.test/predict", 503, "unavailable", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="HTTP 503"):
            evaluate_api.invoke_prediction("https://example.test/predict", VALID, _session())


def _responding(payload: dict):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return mock.patch("urllib.request.urlopen", return_value=response)


def test_invoke_prediction_returns_score_and_class_on_a_valid_response():
    with _responding({"churn_probability": 0.8, "churn": True}):
        result = evaluate_api.invoke_prediction("https://example.test/predict", VALID, _session())

    assert result == {"score": 0.8, "prediction": 1}


def test_invoke_prediction_reports_a_transport_failure():
    with mock.patch("urllib.request.urlopen", side_effect=OSError("connection reset")):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="request failed"):
            evaluate_api.invoke_prediction("https://example.test/predict", VALID, _session())


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"churn_probability": "0.5", "churn": True}, "finite number"),
        ({"churn_probability": True, "churn": True}, "finite number"),
        ({"churn_probability": float("nan"), "churn": True}, "finite number"),
        ({"churn_probability": 1.5, "churn": True}, "between 0 and 1"),
        ({"churn_probability": 0.8, "churn": "yes"}, "must be a boolean"),
    ],
)
def test_invoke_prediction_rejects_contract_violations(payload, expected):
    """Reject each response that violates the prediction contract."""
    with _responding(payload):
        with pytest.raises(evaluate_api.ApiEvaluationError, match=expected):
            evaluate_api.invoke_prediction("https://example.test/predict", VALID, _session())


def test_select_records_requires_room_for_both_classes():
    with pytest.raises(ValueError, match="at least 2"):
        evaluate_api.select_records([_fixture(0, 0), _fixture(1, 1)], limit=1, all_records=False)


def test_select_records_falls_back_to_a_plain_sample_for_one_class():
    """With a single class present, balancing is impossible but sampling must still work."""
    records = [_fixture(0, index) for index in range(10)]

    selected = evaluate_api.select_records(records, limit=4, all_records=False)

    assert len(selected) == 4
    assert [record["row_id"] for record in selected] == sorted(
        record["row_id"] for record in selected
    )


# `main` is the only path an operator runs. These tests cover the argument
# wiring and the fixture URI the report records.

REPORT = {"source": "deployed_api", "accuracy": 1.0}


def test_main_evaluates_an_explicit_fixture_and_prints_the_report(capsys):
    with (
        mock.patch.object(evaluate_api, "load_fixture", return_value=[_fixture(1, 0)]) as load,
        mock.patch.object(evaluate_api, "evaluate_api_records", return_value=dict(REPORT)),
        mock.patch.object(evaluate_api.boto3, "Session", return_value=_session()),
    ):
        evaluate_api.main(["--fixture-s3-uri", "s3://bucket/prefix", "--api-url", "https://x/p"])

    report = json.loads(capsys.readouterr().out)
    # Include the source fixture URI in the report.
    assert report["fixture_s3_uri"] == "s3://bucket/prefix"
    assert load.call_args.args[0] == "s3://bucket/prefix"


def test_main_resolves_the_fixture_from_a_pipeline_execution(capsys):
    with (
        # Keep this split across lines. The trailing comma holds the split.
        # On one line, gitleaks reads it as `api...="<high-entropy string>"`
        # and fails the secret scan on the patch target's own name.
        mock.patch.object(
            evaluate_api,
            "resolve_fixture_s3_uri",
            return_value="s3://bucket/resolved",
        ) as resolve,
        mock.patch.object(evaluate_api, "load_fixture", return_value=[_fixture(1, 0)]),
        mock.patch.object(evaluate_api, "evaluate_api_records", return_value=dict(REPORT)),
        mock.patch.object(evaluate_api.boto3, "Session", return_value=_session()),
    ):
        evaluate_api.main(["--pipeline-execution-arn", "arn:exec", "--api-url", "https://x/p"])

    assert resolve.call_args.args[0] == "arn:exec"
    assert json.loads(capsys.readouterr().out)["fixture_s3_uri"] == "s3://bucket/resolved"


def test_main_writes_the_report_when_output_is_given(tmp_path, capsys):
    output = tmp_path / "report.json"
    with (
        mock.patch.object(evaluate_api, "load_fixture", return_value=[_fixture(1, 0)]),
        mock.patch.object(evaluate_api, "evaluate_api_records", return_value=dict(REPORT)),
        mock.patch.object(evaluate_api.boto3, "Session", return_value=_session()),
    ):
        evaluate_api.main(
            [
                "--fixture-s3-uri",
                "s3://bucket/prefix",
                "--api-url",
                "https://x/p",
                "--output",
                str(output),
            ]
        )

    capsys.readouterr()
    assert json.loads(output.read_text())["source"] == "deployed_api"


@pytest.mark.parametrize(
    "argv",
    [
        ["--fixture-s3-uri", "s3://bucket/prefix"],  # no API URL
        ["--api-url", "https://x/p"],  # no fixture source
    ],
)
def test_main_refuses_to_run_without_a_complete_invocation(argv, monkeypatch):
    """A missing URL must fail here, not as an opaque error mid-evaluation."""
    monkeypatch.delenv("API_URL", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        evaluate_api.main(argv)

    assert exit_info.value.code == 2
