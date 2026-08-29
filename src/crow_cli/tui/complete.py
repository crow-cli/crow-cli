from collections import defaultdict
from typing import Iterable


class Complete:
    """Stores substrings and their potential completions."""

    def __init__(self) -> None:
        self._words: set[str] = set()
        self._word_map: defaultdict[str, set[str]] = defaultdict(set)

    def add_words(self, words: Iterable[str]) -> None:
        """Add word(s) word map.

        Args:
            words: Iterable of words to add.
        """
        self._words.update(words)
        word_map = self._word_map
        for word in words:
            for index in range(1, len(word)):
                word_map[word[:index]].add(word[index:])

    def __call__(self, word: str) -> list[str]:
        if word in self._words:
            return []
        return sorted(self._word_map.get(word, []), key=len, reverse=True)


if __name__ == "__main__":
    complete = Complete()
    complete.add_words(["ls", "ls -al", "echo 'hello'"])

    print(complete("l"))

    from rich import print

    print(complete._word_map)
