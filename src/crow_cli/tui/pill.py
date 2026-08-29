from textual.content import Content


def pill(text: Content | str, background: str, foreground: str) -> Content:
    """Format text as a pill (half block ends).

    Args:
        text: Pill contents as Content object or text.
        background: Background color.
        foreground: Foreground color.

    Returns:
        Pill content.
    """
    content = Content(text) if isinstance(text, str) else text
    main_style = f"{foreground} on {background}"
    end_style = f"{background} on transparent r"
    pill_content = Content.assemble(
        ("▌", end_style),
        content.stylize(main_style),
        ("▐", end_style),
    )
    return pill_content
