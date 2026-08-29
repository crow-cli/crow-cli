from textual.content import Content
from textual.css.styles import RulesMap
from textual.style import Style
from textual.visual import Visual, RenderOptions
from textual.strip import Strip

from itertools import zip_longest


class OptionContent(Visual):
    def __init__(self, option: str | Content, help: str | Content) -> None:
        self.option = Content(option) if isinstance(option, str) else option
        self.help = Content(help) if isinstance(help, str) else help
        self._label = Content(f"{option} {help}")

    def __str__(self) -> str:
        return str(self.option)

    def render_strips(
        self, width: int, height: int | None, style: Style, options: RenderOptions
    ) -> list[Strip]:
        option_strips = [
            Strip(
                self.option.render_segments(style), cell_length=self.option.cell_length
            )
        ]

        option_width = self.option.cell_length
        remaining_width = width - self.option.cell_length

        help_strips = self.help.render_strips(
            remaining_width, None, style, options=options
        )
        help_width = max(strip.cell_length for strip in help_strips)
        help_width = [strip.extend_cell_length(help_width) for strip in help_strips]

        strips: list[Strip] = []
        for option_strip, help_strip in zip_longest(option_strips, help_strips):
            if option_strip is None:
                option_strip = Strip.blank(option_width)
            assert isinstance(help_strip, Strip)
            strips.append(Strip.join([option_strip, help_strip]))
        return strips

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        return self._label.get_optimal_width(rules, container_width)

    def get_height(self, rules: RulesMap, width: int) -> int:
        label_width = self.option.cell_length + 1
        height = self.help.get_height(rules, width - label_width)
        return height
