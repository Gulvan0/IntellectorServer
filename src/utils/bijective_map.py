from typing import Hashable


class BijectionError(Exception):
    def __init__(self, value):
        self.value = value
        msg = 'The value "{}" is already in the mapping.'
        super().__init__(msg.format(value))


class BijectiveMap[L:Hashable, R:Hashable]:
    def __init__(self) -> None:
        self.straight: dict[L, R] = {}
        self.inverse: dict[R, L] = {}

    def add(self, left: L, right: R) -> None:
        if right in self.inverse:
            raise BijectionError(right)

        self.straight[left] = right
        self.inverse[right] = left

    def get[T](self, left: L, default: T | None = None) -> R | T | None:
        return self.straight.get(left, default)

    def get_inverse[T](self, right: R, default: T | None = None) -> L | T | None:
        return self.inverse.get(right, default)

    def leftpop[T](self, left: L, default: T | None = None) -> R | T | None:
        if left in self.straight:
            right = self.straight.pop(left)
            self.inverse.pop(right)
            return right
        return default

    def rightpop[T](self, right: R, default: T | None = None) -> L | T | None:
        if right in self.inverse:
            left = self.inverse.pop(right)
            self.straight.pop(left)
            return left
        return default
