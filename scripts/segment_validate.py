"""章节切分质量验证器（P0-1 质量保险丝）

提供组合验证器检测 LLM 章节切分的常见失败模式：
- catch-all：单章覆盖过多 chunks
- 覆盖问题：chunk 漏/重/越界
- 大小不平衡：章节大小方差过大
- 章节数量不足

用法：
    from segment_validate import validate_outline, OutlineQuality
    
    quality = validate_outline(outline, n_chunks, category="teaching")
    if not quality.valid:
        print(f"验证失败: {quality.failures}")
        # 触发 repair 或 fallback
"""
from __future__ import annotations

import sys

# Windows GBK 编码修复
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from dataclasses import dataclass
from typing import Optional


@dataclass
class OutlineQuality:
    """章节大纲质量评估结果"""
    valid: bool
    score: float  # 0.0-1.0
    warnings: list[str]
    failures: list[str]
    
    # 详细指标
    coverage_valid: bool
    dominant_chapter: Optional[dict]
    size_imbalance: Optional[dict]
    chapter_count_ok: bool
    
    def __str__(self) -> str:
        status = "✓ VALID" if self.valid else "✗ INVALID"
        return (f"{status} (score={self.score:.2f})\n"
                f"  Failures: {self.failures or 'None'}\n"
                f"  Warnings: {self.warnings or 'None'}")


def validate_schema(outline: dict) -> tuple[bool, list[str]]:
    """JSON schema 校验
    
    检查：
    - outline 是 dict
    - 有 "chapters" 字段且为 list
    - 每个 chapter 有 "title" 和 "chunks"
    - chunks 是 int 列表
    
    Returns:
        (valid, errors)
    """
    errors = []
    
    if not isinstance(outline, dict):
        errors.append("outline 不是 dict")
        return False, errors
    
    chapters = outline.get("chapters")
    if not isinstance(chapters, list):
        errors.append("chapters 不是 list")
        return False, errors
    
    if not chapters:
        errors.append("chapters 为空")
        return False, errors
    
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            errors.append(f"chapter[{i}] 不是 dict")
            continue
        
        if "title" not in ch:
            errors.append(f"chapter[{i}] 缺少 title")
        
        if "chunks" not in ch:
            errors.append(f"chapter[{i}] 缺少 chunks")
            continue
        
        chunks = ch["chunks"]
        if not isinstance(chunks, list):
            errors.append(f"chapter[{i}] chunks 不是 list")
            continue
        
        for j, c in enumerate(chunks):
            if not isinstance(c, int):
                errors.append(f"chapter[{i}] chunks[{j}] 不是 int: {c}")
    
    return len(errors) == 0, errors


def validate_coverage(outline: dict, n_chunks: int) -> tuple[bool, list[str]]:
    """覆盖完整性校验
    
    检查：
    - 所有 chunk index 必须被覆盖
    - 不能重复覆盖
    - 不能越界
    - 最好连续覆盖（warning）
    
    Returns:
        (valid, errors)
    """
    errors = []
    chapters = outline.get("chapters", [])
    
    if not chapters:
        errors.append("没有章节")
        return False, errors
    
    used = []
    for i, ch in enumerate(chapters):
        chunks = ch.get("chunks", [])
        for c in chunks:
            if not isinstance(c, int):
                continue
            if c < 0 or c >= n_chunks:
                errors.append(f"chapter[{i}] chunk {c} 越界 (n_chunks={n_chunks})")
            used.append(c)
    
    # 检查重复
    duplicates = [c for c in set(used) if used.count(c) > 1]
    if duplicates:
        errors.append(f"重复覆盖的 chunks: {sorted(duplicates)}")
    
    # 检查遗漏
    expected = set(range(n_chunks))
    actual = set(c for c in used if 0 <= c < n_chunks)
    missing = sorted(expected - actual)
    if missing:
        errors.append(f"遗漏的 chunks: {missing}")
    
    return len(errors) == 0, errors


def detect_dominant_chapter(outline: dict, n_chunks: int,
                            threshold: float = 0.65,
                            min_chunks: int = 10) -> dict:
    """支配章节检测
    
    检测是否有单章覆盖过多 chunks（catch-all 失败模式）
    
    Args:
        outline: 章节大纲
        n_chunks: 总 chunk 数
        threshold: 覆盖比例阈值（默认 0.65 = 65%）
        min_chunks: 最小 chunk 数阈值（短视频不触发）
    
    Returns:
        {
            "is_dominant": bool,
            "ratio": float,
            "max_chapter_idx": int,
            "max_chapter_size": int
        }
    """
    chapters = outline.get("chapters", [])
    
    if not chapters or n_chunks < min_chunks:
        return {
            "is_dominant": False,
            "ratio": 0.0,
            "max_chapter_idx": -1,
            "max_chapter_size": 0
        }
    
    sizes = [(i, len(ch.get("chunks", []))) for i, ch in enumerate(chapters)]
    max_idx, max_size = max(sizes, key=lambda x: x[1])
    ratio = max_size / n_chunks
    
    return {
        "is_dominant": ratio >= threshold,
        "ratio": ratio,
        "max_chapter_idx": max_idx,
        "max_chapter_size": max_size
    }


def detect_size_imbalance(outline: dict) -> dict:
    """章节大小方差检测
    
    检测章节大小是否过于不平衡（某章特别大，其他章特别小）
    
    Returns:
        {
            "suspicious": bool,
            "max_ratio": float,  # max_size / median_size
            "sizes": list[int]
        }
    """
    chapters = outline.get("chapters", [])
    
    if len(chapters) < 2:
        return {
            "suspicious": False,
            "max_ratio": 1.0,
            "sizes": []
        }
    
    sizes = [len(ch.get("chunks", [])) for ch in chapters]
    sorted_sizes = sorted(sizes)
    median_size = sorted_sizes[len(sorted_sizes) // 2]
    
    if median_size == 0:
        return {
            "suspicious": True,
            "max_ratio": float('inf'),
            "sizes": sizes
        }
    
    max_size = max(sizes)
    max_ratio = max_size / median_size
    
    # 阈值：max / median > 4 视为可疑
    return {
        "suspicious": max_ratio > 4.0,
        "max_ratio": max_ratio,
        "sizes": sizes
    }


def check_chapter_count(outline: dict, n_chunks: int,
                        category: str = "teaching") -> tuple[bool, int, int]:
    """章节数量检查
    
    根据 chunk 数和视频类型，检查章节数量是否合理
    
    Args:
        outline: 章节大纲
        n_chunks: 总 chunk 数
        category: 视频类型 (teaching/popsci/vlog/talk)
    
    Returns:
        (ok, actual_count, min_required)
    """
    chapters = outline.get("chapters", [])
    actual = len(chapters)
    
    # 动态计算最少章节数
    if n_chunks >= 4:
        min_required = 3
    elif n_chunks == 3:
        min_required = 2
    else:
        min_required = max(1, n_chunks)
    
    # vlog/talk 可能更碎，允许更多章节
    if category in ("vlog", "talk") and n_chunks >= 13:
        min_required = max(min_required, 5)
    
    return actual >= min_required, actual, min_required


def compute_outline_quality(outline: dict, n_chunks: int,
                            category: str = "teaching") -> OutlineQuality:
    """综合质量评分
    
    组合所有验证器，计算综合质量分数
    
    Args:
        outline: 章节大纲
        n_chunks: 总 chunk 数
        category: 视频类型
    
    Returns:
        OutlineQuality 对象
    """
    warnings = []
    failures = []
    
    # 1. Schema 校验
    schema_ok, schema_errors = validate_schema(outline)
    if not schema_ok:
        return OutlineQuality(
            valid=False,
            score=0.0,
            warnings=[],
            failures=schema_errors,
            coverage_valid=False,
            dominant_chapter=None,
            size_imbalance=None,
            chapter_count_ok=False
        )
    
    # 2. 覆盖完整性
    coverage_ok, coverage_errors = validate_coverage(outline, n_chunks)
    if not coverage_ok:
        failures.extend(coverage_errors)
    
    # 3. 支配章节检测
    dominant = detect_dominant_chapter(outline, n_chunks)
    if dominant["is_dominant"]:
        failures.append(
            f"支配章节检测失败: chapter[{dominant['max_chapter_idx']}] "
            f"覆盖 {dominant['ratio']:.1%} chunks ({dominant['max_chapter_size']}/{n_chunks})"
        )
    
    # 4. 大小不平衡
    imbalance = detect_size_imbalance(outline)
    if imbalance["suspicious"]:
        warnings.append(
            f"章节大小不平衡: max/median = {imbalance['max_ratio']:.1f}, "
            f"sizes = {imbalance['sizes']}"
        )
    
    # 5. 章节数量
    count_ok, actual, min_req = check_chapter_count(outline, n_chunks, category)
    if not count_ok:
        failures.append(
            f"章节数量不足: {actual} < {min_req} (n_chunks={n_chunks})"
        )
    
    # 计算综合分数
    valid = len(failures) == 0
    
    # 分数组成：
    # - 覆盖完整性: 40%
    # - 无支配章节: 30%
    # - 章节数量: 20%
    # - 大小平衡: 10%
    score = 0.0
    if coverage_ok:
        score += 0.4
    if not dominant["is_dominant"]:
        score += 0.3
    if count_ok:
        score += 0.2
    if not imbalance["suspicious"]:
        score += 0.1
    
    return OutlineQuality(
        valid=valid,
        score=score,
        warnings=warnings,
        failures=failures,
        coverage_valid=coverage_ok,
        dominant_chapter=dominant if dominant["is_dominant"] else None,
        size_imbalance=imbalance if imbalance["suspicious"] else None,
        chapter_count_ok=count_ok
    )


def validate_outline(outline: dict, n_chunks: int,
                     category: str = "teaching",
                     verbose: bool = False) -> OutlineQuality:
    """章节大纲验证入口函数
    
    Args:
        outline: LLM 输出的章节大纲
        n_chunks: 总 chunk 数
        category: 视频类型 (teaching/popsci/vlog/talk)
        verbose: 是否打印详细信息
    
    Returns:
        OutlineQuality 对象
    
    Example:
        >>> outline = {"chapters": [{"title": "引入", "chunks": [0, 1]}, ...]}
        >>> quality = validate_outline(outline, n_chunks=10)
        >>> if not quality.valid:
        ...     print(f"验证失败: {quality.failures}")
    """
    quality = compute_outline_quality(outline, n_chunks, category)
    
    if verbose:
        print(f"\n[章节验证] {quality}")
        if quality.dominant_chapter:
            print(f"  支配章节: {quality.dominant_chapter}")
        if quality.size_imbalance:
            print(f"  大小不平衡: {quality.size_imbalance}")
    
    return quality


# ============ 单元测试 ============

def _test_validate_schema():
    """测试 schema 校验"""
    print("\n=== 测试 validate_schema ===")
    
    # 正常 case
    ok, errors = validate_schema({
        "chapters": [
            {"title": "引入", "chunks": [0, 1]},
            {"title": "主体", "chunks": [2, 3, 4]}
        ]
    })
    assert ok, f"应该通过: {errors}"
    print("✓ 正常 case 通过")
    
    # 缺少 chapters
    ok, errors = validate_schema({"foo": "bar"})
    assert not ok
    assert "chapters" in str(errors)
    print("✓ 缺少 chapters 检测通过")
    
    # chunks 不是 list
    ok, errors = validate_schema({
        "chapters": [{"title": "A", "chunks": "invalid"}]
    })
    assert not ok
    print("✓ chunks 类型检测通过")


def _test_validate_coverage():
    """测试覆盖完整性"""
    print("\n=== 测试 validate_coverage ===")
    
    # 正常 case
    ok, errors = validate_coverage({
        "chapters": [
            {"chunks": [0, 1]},
            {"chunks": [2, 3, 4]}
        ]
    }, n_chunks=5)
    assert ok, f"应该通过: {errors}"
    print("✓ 正常覆盖通过")
    
    # 遗漏 chunk
    ok, errors = validate_coverage({
        "chapters": [
            {"chunks": [0, 1]},
            {"chunks": [3, 4]}  # 缺 2
        ]
    }, n_chunks=5)
    assert not ok
    assert "遗漏" in str(errors)
    print("✓ 遗漏检测通过")
    
    # 重复覆盖
    ok, errors = validate_coverage({
        "chapters": [
            {"chunks": [0, 1, 2]},
            {"chunks": [2, 3, 4]}  # 2 重复
        ]
    }, n_chunks=5)
    assert not ok
    assert "重复" in str(errors)
    print("✓ 重复检测通过")
    
    # 越界
    ok, errors = validate_coverage({
        "chapters": [
            {"chunks": [0, 1, 2, 10]}  # 10 越界
        ]
    }, n_chunks=5)
    assert not ok
    assert "越界" in str(errors)
    print("✓ 越界检测通过")


def _test_detect_dominant_chapter():
    """测试支配章节检测"""
    print("\n=== 测试 detect_dominant_chapter ===")
    
    # 正常 case
    result = detect_dominant_chapter({
        "chapters": [
            {"chunks": [0, 1, 2]},
            {"chunks": [3, 4, 5]},
            {"chunks": [6, 7, 8, 9]}
        ]
    }, n_chunks=10)
    assert not result["is_dominant"]
    print(f"✓ 正常分布: ratio={result['ratio']:.2f}")
    
    # catch-all case
    result = detect_dominant_chapter({
        "chapters": [
            {"chunks": [0, 1]},
            {"chunks": list(range(2, 10))}  # 8/10 = 80%
        ]
    }, n_chunks=10)
    assert result["is_dominant"]
    assert result["ratio"] >= 0.65
    print(f"✓ catch-all 检测: ratio={result['ratio']:.2f}")
    
    # 短视频不触发
    result = detect_dominant_chapter({
        "chapters": [
            {"chunks": [0, 1, 2, 3, 4]}  # 5/5 = 100%
        ]
    }, n_chunks=5)
    assert not result["is_dominant"]  # n_chunks < 10
    print("✓ 短视频豁免")


def _test_detect_size_imbalance():
    """测试大小不平衡检测"""
    print("\n=== 测试 detect_size_imbalance ===")
    
    # 正常 case
    result = detect_size_imbalance({
        "chapters": [
            {"chunks": [0, 1]},
            {"chunks": [2, 3]},
            {"chunks": [4, 5, 6]}
        ]
    })
    assert not result["suspicious"]
    print(f"✓ 正常分布: max_ratio={result['max_ratio']:.1f}")
    
    # 不平衡 case
    result = detect_size_imbalance({
        "chapters": [
            {"chunks": [0]},
            {"chunks": [1]},
            {"chunks": list(range(2, 10))}  # 8 vs 1
        ]
    })
    assert result["suspicious"]
    assert result["max_ratio"] > 4.0
    print(f"✓ 不平衡检测: max_ratio={result['max_ratio']:.1f}")


def _test_compute_outline_quality():
    """测试综合质量评分"""
    print("\n=== 测试 compute_outline_quality ===")
    
    # 完美 case
    quality = compute_outline_quality({
        "chapters": [
            {"title": "A", "chunks": [0, 1]},
            {"title": "B", "chunks": [2, 3]},
            {"title": "C", "chunks": [4, 5]}
        ]
    }, n_chunks=6, category="teaching")
    assert quality.valid
    assert quality.score >= 0.9
    print(f"✓ 完美 case: score={quality.score:.2f}")
    
    # catch-all case
    quality = compute_outline_quality({
        "chapters": [
            {"title": "A", "chunks": [0, 1]},
            {"title": "B", "chunks": list(range(2, 12))}  # 10/12 = 83%
        ]
    }, n_chunks=12, category="teaching")
    assert not quality.valid
    assert "支配章节" in str(quality.failures)
    print(f"✓ catch-all 检测: score={quality.score:.2f}, failures={quality.failures}")
    
    # 章节数不足
    quality = compute_outline_quality({
        "chapters": [
            {"title": "A", "chunks": [0, 1, 2]},
            {"title": "B", "chunks": [3, 4, 5]}
        ]
    }, n_chunks=6, category="teaching")
    assert not quality.valid
    assert "章节数量不足" in str(quality.failures)
    print(f"✓ 章节数不足: score={quality.score:.2f}")


if __name__ == "__main__":
    print("运行章节验证器单元测试...")
    _test_validate_schema()
    _test_validate_coverage()
    _test_detect_dominant_chapter()
    _test_detect_size_imbalance()
    _test_compute_outline_quality()
    print("\n✅ 所有测试通过！")

# Made with Bob
