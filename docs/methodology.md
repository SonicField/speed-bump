# Speed Bump Methodology

## The Problem with Traditional Profiling

In GPU-accelerated systems like vLLM or TensorRT-LLM, traditional Python profiling is misleading. A profiler shows where Python spends time, but this doesn't tell you what matters.

Consider: if Python is busy while the GPU is also busy, speeding up Python won't improve throughput. The GPU was the bottleneck. Conversely, if Python is idle while the GPU waits, you won't see Python as "hot" - yet Python *is* the bottleneck.

The fundamental issue is that **time spent ≠ time that matters**.

GPU sampling can help, but sampling rates are too slow to catch micro-stalls - those few microseconds where the GPU sits idle waiting for Python to dispatch the next kernel.

## The Slowdown Approach

Speed Bump inverts the problem: instead of measuring how fast code runs, we measure how much throughput drops when code is artificially slowed.

If slowing down module X doesn't affect throughput, X is not on the critical path - no matter how "hot" it appears in a profiler.

If slowing down module X reduces throughput proportionally, X is a bottleneck worth optimising.

## The Methodology

### Step 1: Establish Baseline and Global Impact

First, determine if Python matters at all.

```bash
# Create a target file that matches everything
echo "*:*" > /tmp/targets.txt

# Run with increasing delays
for delay in 0 1000 10000 100000; do
    SPEED_BUMP_TARGETS=/tmp/targets.txt \
    SPEED_BUMP_DELAY_NS=$delay \
    python benchmark.py
done
```

Plot throughput (tokens/sec, requests/sec, etc.) against delay.

**If throughput is unchanged**: Stop. Python is not your bottleneck. Focus on GPU kernels, memory bandwidth, or I/O.

**If throughput drops**: Proceed to Step 2.

### Step 2: Quantify the Opportunity

With data from Step 1, you can extrapolate to estimate the value of speeding up Python.

```
Throughput
    ^
    |     *  (no delay - baseline)
    |   *
    | *      (increasing delay)
    |*
    +--*--*--*--*----> Delay (ns)
         \
          \ extrapolate backwards
           \
            * (theoretical: if Python were faster)
```

The slope tells you sensitivity. Extrapolating leftward (negative delay = speedup) estimates what faster Python could achieve.

For example, if:
- Baseline throughput: 100 tokens/sec
- With 10µs delay: 95 tokens/sec
- With 100µs delay: 70 tokens/sec

The relationship suggests Python speed matters significantly. Extrapolating, eliminating 10µs of Python overhead per call might yield ~105 tokens/sec.

### Step 3: Isolate Subsystems

Now narrow down which Python subsystem is the bottleneck.

Create targeted pattern files:

```bash
# numpy_targets.txt
numpy.*:*

# zmq_targets.txt
zmq.*:*

# triton_targets.txt
triton.*:*

# model_targets.txt
transformers.modeling_*:*
```

Test each:

```bash
for subsystem in numpy zmq triton model; do
    SPEED_BUMP_TARGETS=/tmp/${subsystem}_targets.txt \
    SPEED_BUMP_DELAY_NS=10000 \
    python benchmark.py
done
```

The subsystem with the largest throughput drop is your primary target.

### Step 4: Focus and Analyse

Once you've identified a subsystem, narrow further:

```bash
# Which specific class/function?
echo "numpy.core.multiarray:*" > /tmp/targets.txt

# Or target specific operations
echo "*:*matmul*" > /tmp/targets.txt
```

Use the frequency setting to reduce noise:

```bash
# Only delay every 10th call - useful for high-frequency functions
SPEED_BUMP_FREQUENCY=10 python benchmark.py
```

### Step 5: Validate and Prioritise

You now have:
1. Evidence that Python optimisation is worthwhile (Step 1-2)
2. A specific subsystem to target (Step 3)
3. Specific functions within that subsystem (Step 4)

This gives you a **smoking gun**: quantitative evidence justifying the optimisation effort, and a clear target.

## Choosing Delay Values

| Delay | Use Case |
|-------|----------|
| 1-10 µs | Fine-grained analysis; detecting micro-stalls |
| 10-100 µs | General subsystem analysis |
| 100 µs - 1 ms | Coarse screening; "does this matter at all?" |
| > 1 ms | Only for very low-frequency operations |

Start coarse (100µs) to get signal quickly, then refine with smaller delays for precision.

## Using Timing Windows

For warmup-sensitive workloads:

```bash
# Skip first 5 seconds (warmup), measure for 30 seconds
SPEED_BUMP_START_MS=5000 \
SPEED_BUMP_DURATION_MS=30000 \
python benchmark.py
```

This avoids polluting results with JIT compilation, cache warming, or connection establishment.

## Interpreting Results

### Linear Relationship
If throughput drops linearly with delay, the targeted code is consistently on the critical path. Every call matters.

### Sub-linear Relationship
If throughput drops less than expected, some calls occur while the GPU is busy (hidden latency). Optimising this code helps, but with diminishing returns.

### No Relationship
If throughput is unchanged, this code is never on the critical path. Don't optimise it.

### Threshold Behaviour
If throughput is stable until a certain delay, then drops sharply, you've found a timing boundary - the point where Python becomes slower than the GPU pipeline can tolerate.

## Example: vLLM Analysis

```bash
# Step 1: Does Python matter?
echo "*:*" > /tmp/all.txt
SPEED_BUMP_TARGETS=/tmp/all.txt SPEED_BUMP_DELAY_NS=10000 \
    python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-7b-hf &
# Run benchmark, measure tokens/sec

# Step 2: Which layer?
for layer in "vllm.worker:*" "vllm.engine:*" "vllm.model_executor:*"; do
    echo "$layer" > /tmp/target.txt
    # restart server, benchmark
done

# Step 3: Narrow down
echo "vllm.model_executor.layers.attention:*" > /tmp/target.txt
# restart server, benchmark

# Result: attention dispatch is sensitive -> investigate CUDA graph boundaries
```

## Limitations

- **Spin delay holds the GIL**: This accurately simulates slower Python, but means other threads are blocked. For multi-threaded analysis, interpret results carefully.

- **PEP 669 overhead**: There's minimal but non-zero overhead for function call interception. For extremely hot functions (millions of calls/sec), this overhead may affect baseline measurements.

- **Pattern matching granularity**: Targets are matched by module path and qualified function name. You cannot target specific call sites or conditional paths within a function.
