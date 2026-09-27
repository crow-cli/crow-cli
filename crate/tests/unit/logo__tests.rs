use super::*;

fn text(line: &Line<'_>) -> String {
    line.spans.iter().map(|s| s.content.as_ref()).collect()
}

fn ink<'a>(line: &'a Line<'a>) -> Vec<&'a Span<'a>> {
    line.spans
        .iter()
        .filter(|span| span.style.fg.is_some())
        .collect()
}

/// The wordmark is rectangular, so centering can't shear it.
#[test]
fn crow_cli_rows_align() {
    for row in CROW_CLI {
        assert_eq!(row.chars().count(), ART_WIDTH, "{row}");
    }
}

/// Wide terminals get the full lockup; narrower ones degrade to a single
/// bold `crow-cli`, then to nothing at all.
#[test]
fn crow_cli_tiers() {
    let theme = Theme::dark();

    let wide = crow_cli_logo_lines(&theme, 80);
    assert_eq!(wide.len(), CROW_CLI.len());
    assert!(
        !wide.iter().any(|line| text(line).contains('█')),
        "the old block art is gone: {:?}",
        wide.iter().map(text).collect::<Vec<_>>()
    );
    let pad = " ".repeat((80 - ART_WIDTH) / 2);
    for (line, row) in wide.iter().zip(CROW_CLI) {
        assert_eq!(text(line), format!("{pad}{row}"));
    }

    // The art needs its own width plus a column of air on either side.
    assert_eq!(
        crow_cli_logo_lines(&theme, (ART_WIDTH + 2) as u16).len(),
        CROW_CLI.len()
    );
    assert_eq!(crow_cli_logo_lines(&theme, (ART_WIDTH + 1) as u16).len(), 1);

    for width in [40u16, 16, 8] {
        let small = crow_cli_logo_lines(&theme, width);
        assert_eq!(small.len(), 1, "one line at width {width}");
        assert_eq!(text(&small[0]).trim(), WORDMARK);
        assert!(
            small[0].spans[1..]
                .iter()
                .all(|span| span.style.add_modifier.contains(Modifier::BOLD)),
            "bold wordmark at width {width}"
        );
    }

    assert!(
        crow_cli_logo_lines(&theme, 7).is_empty(),
        "nothing below the wordmark's own width"
    );
}

/// `crow` carries the brand gradient while `-cli` runs its own ramp in the
/// theme's `ok` hue, so the two words never collapse into one ink.
#[test]
fn crow_cli_runs_a_gradient_per_word() {
    for theme in [Theme::dark(), Theme::light()] {
        for width in [16u16, 40, 80] {
            let lines = crow_cli_logo_lines(&theme, width);
            for line in &lines {
                assert_eq!(ink(line).len(), 2, "`crow` + `-cli` at width {width}");
            }
            if lines.len() == 1 {
                let visible = ink(&lines[0]);
                assert_eq!(visible[0].style.fg, Some(theme.brand), "`crow`");
                assert_eq!(visible[1].style.fg, Some(theme.ok), "`-cli`");
                continue;
            }
            let (ocean_top, ocean_bottom) = match theme.mode {
                Mode::Dark => (DEEPSEEK_50, theme.brand),
                Mode::Light => (theme.brand, DEEPSEEK_200),
            };
            let (mint_top, mint_bottom) = match theme.mode {
                Mode::Dark => (pale(theme.ok), theme.ok),
                Mode::Light => (theme.ok, pale(theme.ok)),
            };
            let first = ink(&lines[0]);
            let last = ink(lines.last().unwrap());
            assert_eq!(first[0].style.fg, Some(ocean_top), "`crow` opens pale");
            assert_eq!(first[1].style.fg, Some(mint_top), "`-cli` opens pale");
            assert_eq!(
                last[0].style.fg,
                Some(ocean_bottom),
                "`crow` closes on brand"
            );
            assert_eq!(last[1].style.fg, Some(mint_bottom), "`-cli` closes on ok");
            assert_ne!(
                first[1].style.fg, last[1].style.fg,
                "`-cli` ramp moves at width {width}"
            );
            assert_ne!(
                first[0].style.fg, first[1].style.fg,
                "the two words stay distinguishable"
            );
        }
    }
}

/// The two-tone split is lossless, and it lands on the word boundary: the
/// hyphen box belongs to `-cli`, so the gradient stops at the `w`.
#[test]
fn crow_cli_split_reassembles_the_wordmark() {
    let theme = Theme::dark();
    let lines = crow_cli_logo_lines(&theme, 80);
    for (line, row) in lines.iter().zip(CROW_CLI) {
        let visible = ink(line);
        assert_eq!(visible[0].content.chars().count(), ART_SPLIT);
        assert_eq!(
            format!("{}{}", visible[0].content, visible[1].content),
            *row
        );
    }

    for (index, row) in CROW_CLI.iter().enumerate() {
        let (crow, cli) = split_row(row, ART_SPLIT);
        assert!(!crow.contains("______"), "row {index} leaks the hyphen");
        assert_eq!(
            cli.contains("______"),
            (2..=4).contains(&index),
            "row {index}"
        );
    }
}
