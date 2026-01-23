# Target Pattern Reference

Speed Bump uses glob patterns to specify which functions to slow down. Each line in a targets file has the format:

```
module_pattern:qualified_name_pattern
```

Both patterns use standard glob syntax (`*`, `?`, `[...]`).

## Pattern Components

### Module Pattern

The module pattern matches against the **file path** of the code object. This is typically the full path to the `.py` file.

| Pattern | Matches |
|---------|---------|
| `*` | Any module |
| `*/numpy/*` | Any file in a numpy directory |
| `*transformers*` | Any file with "transformers" in the path |
| `/home/user/myproject/*.py` | Specific directory |

### Qualified Name Pattern

The qualified name pattern matches against the function's `co_qualname`, which includes:
- The function name
- Enclosing class names (for methods)
- Enclosing function names (for nested functions)

| Code | Qualified Name |
|------|----------------|
| `def foo(): ...` | `foo` |
| `class Bar: def baz(self): ...` | `Bar.baz` |
| `def outer(): def inner(): ...` | `outer.<locals>.inner` |
| `class A: class B: def m(self): ...` | `A.B.m` |

## Pattern Examples

### Match Everything

```
*:*
```

Useful for Step 1 analysis: "does Python matter at all?"

### Match a Specific Function

```
*/vllm/worker/model_runner.py:ModelRunner.execute_model
```

### Match All Methods of a Class

```
*:ModelRunner.*
```

Matches `ModelRunner.execute_model`, `ModelRunner.__init__`, etc.

### Match Anything Containing a Substring

```
*:*attention*
```

Matches any function with "attention" in its qualified name (case-sensitive).

### Match a Module

```
*/numpy/*:*
```

Matches all functions in numpy.

### Match Nested Functions

Because nested functions include `<locals>` in their qualified name:

```
*:*<locals>*
```

Matches all nested/local functions.

Or to match a specific nested function:

```
*:*outer.<locals>.inner
```

### Match Test Functions

```
*/tests/*:test_*
```

### Exclude Patterns

There's no exclude syntax. If you need to exclude, create a target file with only what you want to include.

## Target File Format

```
# Comments start with #
# Blank lines are ignored

# One pattern per line
*:ModelRunner.*
*/transformers/*:*Attention*

   # Whitespace is stripped
   *:some_function
```

## Debugging Patterns

If your pattern isn't matching as expected:

1. Check the qualified name by adding a print in your code:
   ```python
   import sys
   print(my_function.__code__.co_qualname)
   ```

2. Check the file path:
   ```python
   print(my_function.__code__.co_filename)
   ```

3. Use a broad pattern first, then narrow down:
   ```
   *:*  # matches everything - verify setup works
   *:*MyClass*  # narrow to class
   *:MyClass.my_method  # narrow to method
   ```

## Common Patterns by Framework

### vLLM

```
# All worker operations
*/vllm/worker/*:*

# Model execution
*:ModelRunner.execute_model

# Attention layers
*:*Attention*
```

### Transformers

```
# All modeling code
*/transformers/models/*:*

# Specific architecture
*/transformers/models/llama/*:*

# Attention mechanisms
*:*Attention.forward
```

### PyTorch

```
# Tensor operations (Python side)
*/torch/*:*

# Specific modules
*:Linear.forward
*:Conv2d.forward
```

### NumPy

```
# All numpy
*/numpy/*:*

# Core operations
*/numpy/core/*:*
```
