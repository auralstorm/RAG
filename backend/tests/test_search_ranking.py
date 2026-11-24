"""Verify the agreed RRF fusion boundary with independently worked examples."""

import pytest
from app.adapters.elasticsearch import reciprocal_rank_fusion


def test_fusion_rewards_agreement_without_comparing_incompatible_scores() -> None:
    result = reciprocal_rank_fusion(("a", "b"), ("b", "c"), rank_constant=1)
    assert [hit.chunk_id for hit in result] == ["b", "a", "c"]
    assert result[0].score == pytest.approx(5 / 6)
    assert (result[0].dense_rank, result[0].bm25_rank) == (2, 1)


def test_duplicate_chunks_do_not_receive_extra_votes_or_shift_unique_ranks() -> None:
    result = reciprocal_rank_fusion(("a", "a", "b"), ("a", "b", "b"), rank_constant=1)
    assert [hit.chunk_id for hit in result] == ["a", "b"]
    assert result[0].score == pytest.approx(1)
    assert result[1].score == pytest.approx(2 / 3)
    assert (result[1].dense_rank, result[1].bm25_rank) == (2, 2)


def test_ties_are_stable_and_an_empty_branch_is_supported() -> None:
    assert [hit.chunk_id for hit in reciprocal_rank_fusion(("b",), ("a",))] == ["a", "b"]
    assert reciprocal_rank_fusion((), ()) == []
    assert reciprocal_rank_fusion(("a",), ())[0].score == pytest.approx(1 / 61)


@pytest.mark.parametrize("constant", [0, -1])
def test_invalid_rank_constant_is_rejected(constant: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        reciprocal_rank_fusion(("a",), (), rank_constant=constant)
