/* PowerSort: adaptive multi-algorithm sorter (timsort-class power, explicit).
 * Dispatcher samples keys and picks the strongest tool:
 *   integers, small range -> counting sort (O(n+k), stable)
 *   integers, wide range  -> radix sort LSD base-256 (O(4n), stable)
 *   finite floats         -> bucket sort (avg O(n), stable)
 *   locale/text keys      -> merge sort (stable, O(n log n))
 *   comparator-only       -> introsort: quicksort (median-of-3) with
 *                            heapsort fallback past 2*log2(n) depth (O(n log n) worst)
 * Exposed individually for tests; adaptive via PowerSort.sortBy().
 */
(function (root) {
  "use strict";

  function insertion(a, lo, hi, cmp) {
    for (let i = lo + 1; i <= hi; i++) {
      const x = a[i];
      let j = i - 1;
      while (j >= lo && cmp(x, a[j]) < 0) { a[j + 1] = a[j]; j--; }
      a[j + 1] = x;
    }
  }

  function median3(a, lo, hi, cmp) {
    const m = (lo + hi) >> 1;
    if (cmp(a[m], a[lo]) < 0) { const t = a[lo]; a[lo] = a[m]; a[m] = t; }
    if (cmp(a[hi], a[lo]) < 0) { const t = a[lo]; a[lo] = a[hi]; a[hi] = t; }
    if (cmp(a[hi], a[m]) < 0) { const t = a[m]; a[m] = a[hi]; a[hi] = t; }
    return m;
  }

  function partition(a, lo, hi, cmp) {
    const m = median3(a, lo, hi, cmp);
    const t = a[m]; a[m] = a[hi - 1]; a[hi - 1] = t;
    const pivot = a[hi - 1];
    let i = lo, j = hi - 1;
    for (;;) {
      while (cmp(a[++i], pivot) < 0) {}
      while (cmp(pivot, a[--j]) < 0) {}
      if (i >= j) break;
      const s = a[i]; a[i] = a[j]; a[j] = s;
    }
    const s = a[i]; a[i] = a[hi - 1]; a[hi - 1] = s;
    return i;
  }

  function siftDown(a, root_, size, cmp, base) {
    for (;;) {
      const l = base + 2 * (root_ - base) + 1;
      const r = l + 1;
      let big = root_;
      if (l < base + size && cmp(a[l], a[big]) > 0) big = l;
      if (r < base + size && cmp(a[r], a[big]) > 0) big = r;
      if (big === root_) return;
      const t = a[root_]; a[root_] = a[big]; a[big] = t;
      root_ = big;
    }
  }

  function heapSort(a, cmp, lo, hi) {
    lo = lo || 0; hi = hi === undefined ? a.length - 1 : hi;
    const n = hi - lo + 1;
    for (let i = (n >> 1) - 1; i >= 0; i--) siftDown(a, lo + i, n, cmp, lo);
    for (let end = n - 1; end > 0; end--) {
      const t = a[lo]; a[lo] = a[lo + end]; a[lo + end] = t;
      siftDown(a, lo, end, cmp, lo);
    }
    return a;
  }

  function quickSort(a, cmp, lo, hi) {
    lo = lo || 0; hi = hi === undefined ? a.length - 1 : hi;
    while (hi - lo > 16) {
      const p = partition(a, lo, hi, cmp);
      if (p - lo < hi - p) { quickSort(a, cmp, lo, p - 1); lo = p + 1; }
      else { quickSort(a, cmp, p + 1, hi); hi = p - 1; }
    }
    insertion(a, lo, hi, cmp);
    return a;
  }

  function introsort(a, cmp) {
    cmp = cmp || ((x, y) => (x < y ? -1 : x > y ? 1 : 0));
    const depth = 2 * Math.floor(Math.log2(a.length || 1));
    (function loop(lo, hi, d) {
      while (hi - lo > 16) {
        if (d <= 0) { heapSort(a, cmp, lo, hi); return; }
        const p = partition(a, lo, hi, cmp);
        if (p - lo < hi - p) { loop(lo, p - 1, d - 1); lo = p + 1; }
        else { loop(p + 1, hi, d - 1); hi = p - 1; }
      }
      insertion(a, lo, hi, cmp);
    })(0, a.length - 1, depth);
    return a;
  }

  function mergeSort(a, cmp) {
    cmp = cmp || ((x, y) => (x < y ? -1 : x > y ? 1 : 0));
    const aux = a.slice();
    (function rec(lo, hi) {
      if (hi - lo < 2) return;
      const mid = (lo + hi) >> 1;
      rec(lo, mid); rec(mid, hi);
      let i = lo, j = mid, k = lo;
      while (i < mid && j < hi) {
        if (cmp(aux[j], aux[i]) < 0) a[k++] = aux[j++];
        else a[k++] = aux[i++];
      }
      while (i < mid) a[k++] = aux[i++];
      while (j < hi) a[k++] = aux[j++];
      for (let t = lo; t < hi; t++) aux[t] = a[t];
    })(0, a.length);
    return a;
  }

  function orderByInt(keys, pick) {
    let mn = Infinity, mx = -Infinity;
    for (let i = 0; i < keys.length; i++) {
      const v = pick(keys[i]);
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
    return [mn, mx];
  }

  function countingSort(arr, key) {
    const n = arr.length;
    const [mn, mx] = orderByInt(arr, key);
    const range = mx - mn + 1;
    const cnt = new Array(range).fill(0);
    for (let i = 0; i < n; i++) cnt[key(arr[i]) - mn]++;
    for (let i = 1; i < range; i++) cnt[i] += cnt[i - 1];
    const out = new Array(n);
    for (let i = n - 1; i >= 0; i--) out[--cnt[key(arr[i]) - mn]] = arr[i];
    for (let i = 0; i < n; i++) arr[i] = out[i];
    return { algo: "counting", range: range };
  }

  function radixSort(arr, key) {
    const n = arr.length;
    let idx = new Array(n), nxt = new Array(n);
    for (let i = 0; i < n; i++) idx[i] = i;
    const cnt = new Array(256);
    for (let pass = 0; pass < 4; pass++) {
      cnt.fill(0);
      const sh = pass * 8;
      for (let i = 0; i < n; i++) cnt[((key(arr[idx[i]]) | 0) ^ 0x80000000) >>> sh & 0xff]++;
      let s = 0;
      for (let i = 0; i < 256; i++) { const c = cnt[i]; cnt[i] = s; s += c; }
      for (let i = 0; i < n; i++) nxt[cnt[((key(arr[idx[i]]) | 0) ^ 0x80000000) >>> sh & 0xff]++] = idx[i];
      const t = idx; idx = nxt; nxt = t;
    }
    const out = new Array(n);
    for (let i = 0; i < n; i++) out[i] = arr[idx[i]];
    for (let i = 0; i < n; i++) arr[i] = out[i];
    return { algo: "radix" };
  }

  function bucketSort(arr, key) {
    const n = arr.length;
    const [mn, mx] = orderByInt(arr, key);
    if (!(mx > mn)) return { algo: "bucket-trivial" };
    const buckets = new Array(n);
    for (let i = 0; i < n; i++) buckets[i] = [];
    for (let i = 0; i < n; i++) {
      let b = Math.floor(((key(arr[i]) - mn) / (mx - mn)) * n);
      if (b >= n) b = n - 1;
      buckets[b].push(i);
    }
    const out = new Array(n);
    let p = 0;
    const cmp = (i, j) => key(arr[i]) - key(arr[j]);
    for (let b = 0; b < n; b++) {
      const bk = buckets[b];
      for (let i = 1; i < bk.length; i++) {
        const x = bk[i];
        let j = i - 1;
        while (j >= 0 && cmp(x, bk[j]) < 0) { bk[j + 1] = bk[j]; j--; }
        bk[j + 1] = x;
      }
      for (let i = 0; i < bk.length; i++) out[p++] = arr[bk[i]];
    }
    for (let i = 0; i < n; i++) arr[i] = out[i];
    return { algo: "bucket" };
  }

  function sortBy(arr, key, cmp, opts) {
    opts = opts || {};
    if (arr.length < 2) return { algo: "trivial" };
    key = key || ((x) => x);
    const sample = Math.min(arr.length, 64);
    let ints = 0, floats = 0;
    for (let i = 0; i < sample; i++) {
      const v = key(arr[(i * 2654435761) % arr.length]);
      if (typeof v === "number" && isFinite(v)) {
        if (Math.floor(v) === v && Math.abs(v) < 2147483648) ints++;
        else floats++;
      }
    }
    if (ints === sample) {
      const [mn, mx] = orderByInt(arr, key);
      if (mx - mn + 1 <= 4 * arr.length) return countingSort(arr, key);
      return radixSort(arr, key);
    }
    if (ints + floats === sample) return bucketSort(arr, key);
    if (opts.stable === false) {
      introsort(arr, cmp && ((a, b) => cmp(key(a), key(b))));
      return { algo: "introsort" };
    }
    mergeSort(arr, cmp && ((a, b) => cmp(key(a), key(b))));
    return { algo: "merge" };
  }

  root.PowerSort = {
    sortBy: sortBy,
    introsort: introsort,
    quickSort: quickSort,
    heapSort: heapSort,
    mergeSort: mergeSort,
    countingSort: countingSort,
    radixSort: radixSort,
    bucketSort: bucketSort,
  };
})(typeof window !== "undefined" ? window : globalThis);
if (typeof module !== "undefined" && module.exports) {
  module.exports = globalThis.PowerSort;
}
