import json
import urllib.error
from unittest import mock

import pytest

from scripts import evaluate_api
from tests.unit.conftest import VALID


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
    """A malformed URI must fail here, not as a confusing S3 404 later."""
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

    # Looked up by job name, not by the full ARN.
    assert client.describe_processing_job.call_args.kwargs == {"ProcessingJobName": "prep-1"}


def test_resolve_fixture_s3_uri_fails_when_the_execution_has_no_api_test_output():
    """An execution predating the fixture output must say so, not return None."""
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
    # A prefix gets the fixture filename appended; blank lines are skipped.
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
    """An empty fixture would otherwise report a perfect score over zero records."""
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
        report = evaluate_api.evaluate_api_records(records, "https://example.test/predict", "key")

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
            evaluate_api.invoke_prediction("https://example.test/predict", "key", VALID)


def test_invoke_prediction_reports_http_failure():
    error = urllib.error.HTTPError("https://example.test/predict", 503, "unavailable", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="HTTP 503"):
            evaluate_api.invoke_prediction("https://example.test/predict", "key", VALID)
