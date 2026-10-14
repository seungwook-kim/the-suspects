from server.llm.partial_json import complete_sentences, partial_string_field


def test_partial_string_field_reads_growing_value():
    raw = '{"emotion": "nervous", "text": "그게요... 집에'
    assert partial_string_field(raw, "emotion") == ("nervous", True)
    assert partial_string_field(raw, "text") == ("그게요... 집에", False)
    assert partial_string_field('{"emotion": "ne', "text") is None


def test_partial_string_field_escapes_and_cut_escape():
    assert partial_string_field('{"text": "그가 \\"왜\\"라고\\n했다"}', "text") == ('그가 "왜"라고\n했다', True)
    assert partial_string_field('{"text": "a\\', "text") == ("a", False)  # 잘린 이스케이프는 기다린다
    assert partial_string_field('{"text": "\\uAC00\\uAC', "text") == ("가", False)


def test_complete_sentences_only_finished_ones():
    assert complete_sentences("집에 있었어요. 혼자서", False) == "집에 있었어요."
    assert complete_sentences("그게요... 확실하진 않은데", False) == "그게요..."
    assert complete_sentences("왜 물으세요? 저는", False) == "왜 물으세요?"
    assert complete_sentences("아직 한 문장도 안 끝남", False) == ""
    assert complete_sentences("마지막 문장은 끝 표시가 없어도 ", True) == "마지막 문장은 끝 표시가 없어도"
