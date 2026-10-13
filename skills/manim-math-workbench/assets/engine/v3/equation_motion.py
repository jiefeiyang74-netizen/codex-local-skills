"""Pure, bounded contracts for copying equations and adding their two sides.

No evaluation of model text. The mapping preserves every source term in order;
only the redundant second equality sign is removed. Also injected into exports.
"""
import re


def equation_motion_tokens(text):
    pattern = (r"\{\{[a-z][a-z0-9_]*\}\}|[＋+－−\-×*÷/＝=（）()\[\]]|"
               r"\d+(?:\.\d+)?(?:万|亿|千|百)?(?:美元|元|份)?|"
               r"[^\s＋+－−\-×*÷/＝=（）()\[\]\d{}]+")
    aliases = {"=": "＝", "+": "＋", "(": "（", ")": "）"}
    return [aliases.get(token, token) for token in re.findall(pattern, str(text))]


def equation_sum_mapping(first, second, target=None):
    """Return [(token, source_slot_or_None, source_token_index_or_None)]."""
    sources = [equation_motion_tokens(first), equation_motion_tokens(second)]
    equals = []
    for tokens in sources:
        if tokens.count("＝") != 1 or not 3 <= len(tokens) <= 48:
            raise ValueError("搬运来源必须是只有一个等号、左右两边完整的等式")
        index = tokens.index("＝")
        if index == 0 or index == len(tokens) - 1:
            raise ValueError("等式左右两边不能为空")
        equals.append(index)
    result = []
    def added(token):
        result.append((token, None, None))
    for slot, (tokens, equal) in enumerate(zip(sources, equals)):
        if slot:
            added("＋")
        added("（")
        result.extend((tokens[i], slot, i) for i in range(equal))
        added("）")
    result.append(("＝", 0, equals[0]))
    for slot, (tokens, equal) in enumerate(zip(sources, equals)):
        if slot:
            added("＋")
        wrapped = len(tokens) - equal - 1 > 1
        if wrapped:
            added("（")
        result.extend((tokens[i], slot, i) for i in range(equal + 1, len(tokens)))
        if wrapped:
            added("）")
    expected = [entry[0] for entry in result]
    if target is not None and equation_motion_tokens(target) != expected:
        raise ValueError("合并须保留两式左右项和顺序，不能提前计算或漏项；目标应为：" + "".join(expected))
    return result
