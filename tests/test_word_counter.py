"""Tests for utils/word_counter.py"""

from utils.word_counter import count_words


def test_empty_and_none_return_zero():
    assert count_words("") == 0
    assert count_words(None) == 0
    assert count_words("   \n\t  ") == 0


def test_simple_sentence():
    assert count_words("I like English very much") == 5


def test_standalone_punctuation_is_not_counted():
    assert count_words("Hello, world -- today ...") == 3


def test_numbers_are_counted():
    assert count_words("I have 3 books and 20 pens") == 7


def test_multiple_lines_are_counted():
    text = "Dear Sir,\n\nI am writing to ask about the course."
    assert count_words(text) == 10
