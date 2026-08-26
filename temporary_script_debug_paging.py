"""
验证：小众历史片（最终 n<100）在 n=N_AT 时，模型预测最终分 vs 真实最终分。
回答：小众片能不能在早期（n=N_AT）就交易（分数是否已稳定、可预测）。
排除 config 里 exclude_from_backtest=True 的片。

USE_FIXED_NFINAL 开关：
  True  → 用 FIXED_NFINAL_GUESS（模拟实盘：你不知道真实n，统一猜一个值）
  False → 用真实 total_n（上帝视角：假设完美预知最终评论数，看模型上限）

用法：py temporary_script_debug_paging.py
"""

"""验证平台适配器：两个平台都能 get_rungs + yes_prob。"""
"""查config里resident_evil的UUID实际指向哪部片。"""
"""查 resident_evil_2026 页面所有 JSON-LD Movie 块。"""
def add_k_probability(counts, context, word, k, vocab_size):
    ctx = counts.get(context, {})
    return (ctx.get(word, 0) + k) / (sum(ctx.values()) + k * vocab_size)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def run_tests():
    passed = 0
    total = 0
    counts = {"the": {"cat": 5, "dog": 3, "bird": 2}}

    # Test 1: seen bigram (5+1)/(10+100)
    total += 1
    r = add_k_probability(counts, "the", "cat", 1, 100)
    if approx(r, 6 / 110):
        passed += 1
        print("Test 1 PASS:", r)
    else:
        print("Test 1 FAIL:", r, "expected", 6 / 110)

    # Test 2: unseen context (0+1)/(0+100)
    total += 1
    r = add_k_probability(counts, "runs", "fast", 1, 100)
    if approx(r, 0.01):
        passed += 1
        print("Test 2 PASS:", r)
    else:
        print("Test 2 FAIL:", r, "expected 0.01")

    # Test 3: seen context, unseen word (0+1)/(10+100)
    total += 1
    r = add_k_probability(counts, "the", "fish", 1, 100)
    if approx(r, 1 / 110):
        passed += 1
        print("Test 3 PASS:", r)
    else:
        print("Test 3 FAIL:", r, "expected", 1 / 110)

    # Test 4: fractional k (add-k with k<1), (3+0.5)/(10+0.5*100)
    total += 1
    r = add_k_probability(counts, "the", "dog", 0.5, 100)
    if approx(r, 3.5 / 60):
        passed += 1
        print("Test 4 PASS:", r)
    else:
        print("Test 4 FAIL:", r, "expected", 3.5 / 60)

    # Test 5: distribution over vocab sums to 1
    total += 1
    V = 100
    vocab = ["cat", "dog", "bird"] + [f"w{i}" for i in range(V - 3)]
    total_prob = sum(add_k_probability(counts, "the", w, 1, V) for w in vocab)
    if approx(total_prob, 1.0):
        passed += 1
        print("Test 5 PASS: sum over vocab =", total_prob)
    else:
        print("Test 5 FAIL: sum =", total_prob, "expected 1.0")

    print(f"\n{passed}/{total} tests passed")


if __name__ == "__main__":
    run_tests()