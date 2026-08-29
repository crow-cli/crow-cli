from textual.widgets import Label


class NonSelectableLabel(Label):
    ALLOW_SELECT = False
