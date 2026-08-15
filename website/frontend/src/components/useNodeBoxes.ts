// Measure where the architecture nodes actually are.
//
// The routes between stages MUST touch the nodes they connect. Percentage
// coordinates cannot do that: the node row is a grid with a `clamp()` gap, so
// a column centre is not a fixed fraction of the width at any breakpoint, and
// the bitmap display font changes each node's height when it finishes loading.
//
// This hook reads the real boxes instead. The caller draws its routes in the
// same pixel space, so one set of path builders serves the horizontal desktop
// row and the stacked mobile column with no second coordinate system.

import { useCallback, useEffect, useRef, useState } from "react";

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Geometry<K extends string> {
  /** The container's own size, and the SVG viewBox the caller draws into. */
  width: number;
  height: number;
  boxes: Partial<Record<K, Box>>;
}

export interface NodeBoxes<K extends string> {
  containerRef: (node: HTMLElement | null) => void;
  registerNode: (key: K) => (node: HTMLElement | null) => void;
  geometry: Geometry<K>;
}

const EMPTY: Geometry<string> = { width: 0, height: 0, boxes: {} };

export function useNodeBoxes<K extends string>(): NodeBoxes<K> {
  const container = useRef<HTMLElement | null>(null);
  const nodes = useRef(new Map<K, HTMLElement>());
  const observer = useRef<ResizeObserver | null>(null);
  const frame = useRef(0);
  // Each key keeps one callback for the life of the hook. A fresh function
  // identity on every render would make React detach and reattach the ref,
  // and each reattach schedules another measurement.
  const callbacks = useRef(new Map<K, (node: HTMLElement | null) => void>());
  const [geometry, setGeometry] = useState<Geometry<K>>(EMPTY as Geometry<K>);

  const measure = useCallback(() => {
    const root = container.current;
    if (!root) return;
    const origin = root.getBoundingClientRect();
    const boxes: Partial<Record<K, Box>> = {};
    for (const [key, node] of nodes.current) {
      const rect = node.getBoundingClientRect();
      boxes[key] = {
        x: rect.left - origin.left,
        y: rect.top - origin.top,
        width: rect.width,
        height: rect.height,
      };
    }
    setGeometry((previous) => {
      const next = { width: origin.width, height: origin.height, boxes };
      // A ResizeObserver fires on every paint that touches the subtree. An
      // unchanged value here would still rerender the whole map.
      return sameGeometry(previous, next) ? previous : next;
    });
  }, []);

  // Reading a box forces layout, so several registrations in one commit
  // collapse into a single measurement on the next frame.
  const schedule = useCallback(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      measure();
    });
  }, [measure]);

  // One observer watches the container and every node. Fonts resolve after
  // first paint, so `document.fonts.ready` triggers the remeasure that the
  // taller bitmap labels need.
  useEffect(() => {
    const watch = new ResizeObserver(schedule);
    observer.current = watch;
    if (container.current) watch.observe(container.current);
    for (const node of nodes.current.values()) watch.observe(node);
    schedule();

    window.addEventListener("resize", schedule);
    document.fonts?.ready.then(schedule).catch(() => undefined);
    return () => {
      window.removeEventListener("resize", schedule);
      watch.disconnect();
      observer.current = null;
      if (frame.current) cancelAnimationFrame(frame.current);
      frame.current = 0;
    };
  }, [schedule]);

  const containerRef = useCallback(
    (node: HTMLElement | null) => {
      const watch = observer.current;
      if (container.current && watch) watch.unobserve(container.current);
      container.current = node;
      if (node && watch) watch.observe(node);
      schedule();
    },
    [schedule],
  );

  const registerNode = useCallback(
    (key: K) => {
      let callback = callbacks.current.get(key);
      if (!callback) {
        callback = (node: HTMLElement | null) => {
          const watch = observer.current;
          const previous = nodes.current.get(key);
          if (previous && watch) watch.unobserve(previous);
          if (node) {
            nodes.current.set(key, node);
            if (watch) watch.observe(node);
          } else {
            nodes.current.delete(key);
          }
          schedule();
        };
        callbacks.current.set(key, callback);
      }
      return callback;
    },
    [schedule],
  );

  return { containerRef, registerNode, geometry };
}

function sameGeometry<K extends string>(a: Geometry<K>, b: Geometry<K>): boolean {
  if (a.width !== b.width || a.height !== b.height) return false;
  const keys = Object.keys(b.boxes) as K[];
  if (keys.length !== Object.keys(a.boxes).length) return false;
  return keys.every((key) => {
    const one = a.boxes[key];
    const two = b.boxes[key];
    if (!one || !two) return false;
    return (
      one.x === two.x && one.y === two.y && one.width === two.width && one.height === two.height
    );
  });
}

/** Read the midpoint of a box's right edge. */
export const rightOf = (box: Box) => ({ x: box.x + box.width, y: box.y + box.height / 2 });

/** Read the midpoint of a box's left edge. */
export const leftOf = (box: Box) => ({ x: box.x, y: box.y + box.height / 2 });

/** Read the midpoint of a box's bottom edge. */
export const bottomOf = (box: Box) => ({ x: box.x + box.width / 2, y: box.y + box.height });

/** Read the midpoint of a box's top edge. */
export const topOf = (box: Box) => ({ x: box.x + box.width / 2, y: box.y });
