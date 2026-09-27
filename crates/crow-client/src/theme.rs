//! DeepSeek Harness Web UI design tokens, mapped 1:1 from
//! `packages/client/ui-theme/src/styles/design-platform.css`.
//!
//! Static palette (`--dsw-static-*`) plus semantic themes: a cold
//! neutral-bluish base kept deliberately quiet, with a small reserved
//! accent vocabulary — DeepSeek blue for brand/actions, gray-blue for
//! hints, green for success/liveness, amber for attention, red for
//! errors. Minimal, not monotone.

use ratatui::style::Color;
use serde_json::Value;

// --- static palette -------------------------------------------------------

#[allow(dead_code)]
pub const DEEPSEEK_50: Color = Color::Rgb(237, 243, 254);
#[allow(dead_code)]
pub const DEEPSEEK_100: Color = Color::Rgb(228, 237, 253);
#[allow(dead_code)]
pub const DEEPSEEK_200: Color = Color::Rgb(211, 226, 255);
#[allow(dead_code)]
pub const DEEPSEEK_300: Color = Color::Rgb(183, 200, 254);
#[allow(dead_code)]
pub const DEEPSEEK_400: Color = Color::Rgb(103, 158, 254);
#[allow(dead_code)]
pub const DEEPSEEK_450: Color = Color::Rgb(86, 134, 254);
#[allow(dead_code)]
pub const DEEPSEEK_500: Color = Color::Rgb(65, 118, 230);
#[allow(dead_code)]
pub const DEEPSEEK_600: Color = Color::Rgb(72, 104, 178);
#[allow(dead_code)]
pub const DEEPSEEK_800: Color = Color::Rgb(52, 65, 91);
#[allow(dead_code)]
pub const DEEPSEEK_900: Color = Color::Rgb(40, 49, 66);

#[allow(dead_code)]
pub const BLUISH_00: Color = Color::Rgb(255, 255, 255);
#[allow(dead_code)]
pub const BLUISH_50: Color = Color::Rgb(249, 250, 251);
#[allow(dead_code)]
pub const BLUISH_60: Color = Color::Rgb(245, 246, 247);
#[allow(dead_code)]
pub const BLUISH_75: Color = Color::Rgb(241, 243, 245);
#[allow(dead_code)]
pub const BLUISH_100: Color = Color::Rgb(235, 238, 242);
#[allow(dead_code)]
pub const BLUISH_150: Color = Color::Rgb(233, 236, 242);
#[allow(dead_code)]
pub const BLUISH_200: Color = Color::Rgb(225, 229, 238);
#[allow(dead_code)]
pub const BLUISH_300: Color = Color::Rgb(207, 211, 214);
#[allow(dead_code)]
pub const BLUISH_400: Color = Color::Rgb(173, 178, 184);
#[allow(dead_code)]
pub const BLUISH_500: Color = Color::Rgb(151, 157, 166);
#[allow(dead_code)]
pub const BLUISH_600: Color = Color::Rgb(129, 133, 140);
#[allow(dead_code)]
pub const BLUISH_700: Color = Color::Rgb(97, 102, 107);
#[allow(dead_code)]
pub const BLUISH_750: Color = Color::Rgb(67, 69, 74);
#[allow(dead_code)]
pub const BLUISH_800: Color = Color::Rgb(53, 54, 56);
#[allow(dead_code)]
pub const BLUISH_850: Color = Color::Rgb(44, 44, 46);
#[allow(dead_code)]
pub const BLUISH_875: Color = Color::Rgb(35, 35, 36);
#[allow(dead_code)]
pub const BLUISH_900: Color = Color::Rgb(27, 27, 28);
#[allow(dead_code)]
pub const BLUISH_950: Color = Color::Rgb(21, 21, 23);
#[allow(dead_code)]
pub const BLUISH_1000: Color = Color::Rgb(15, 17, 21);

#[allow(dead_code)]
pub const RED_400: Color = Color::Rgb(242, 90, 90);
#[allow(dead_code)]
pub const RED_500: Color = Color::Rgb(239, 68, 68);
#[allow(dead_code)]
pub const RED_600: Color = Color::Rgb(236, 19, 19);
#[allow(dead_code)]
pub const GREEN_400: Color = Color::Rgb(78, 209, 126);
#[allow(dead_code)]
pub const GREEN_500: Color = Color::Rgb(34, 197, 94);
#[allow(dead_code)]
pub const AMBER_400: Color = Color::Rgb(247, 173, 49);
#[allow(dead_code)]
pub const AMBER_500: Color = Color::Rgb(245, 158, 11);
#[allow(dead_code)]
pub const AMBER_600: Color = Color::Rgb(221, 134, 41);

/// Blue-gray (slate) hint tones — gray first, a cool blue undertone;
/// clearly quieter than the DeepSeek blues.
pub const SLATE_400: Color = Color::Rgb(108, 122, 150);
pub const SLATE_600: Color = Color::Rgb(84, 96, 120);

// --- semantic theme -------------------------------------------------------

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Mode {
    Dark,
    Light,
}

impl Mode {
    pub fn as_str(self) -> &'static str {
        match self {
            Mode::Dark => "dark",
            Mode::Light => "light",
        }
    }

    pub fn parse(s: &str) -> Option<Mode> {
        match s {
            "dark" => Some(Mode::Dark),
            "light" => Some(Mode::Light),
            _ => None,
        }
    }
}

/// Closed token names for protocol 0 palettes (`tuiTheme.register` / Cordis theme update).
pub const TOKEN_NAMES: &[&str] = &[
    "bg",
    "surface",
    "panel",
    "fg",
    "fg_secondary",
    "fg_tertiary",
    "caption",
    "brand",
    "brand_soft",
    "bubble_bg",
    "bubble_fg",
    "border",
    "code_bg",
    "ok",
    "warn",
    "err",
    "hint",
    "chip_bg",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct TokenMap {
    bg: Color,
    surface: Color,
    panel: Color,
    fg: Color,
    fg_secondary: Color,
    fg_tertiary: Color,
    caption: Color,
    brand: Color,
    brand_soft: Color,
    bubble_bg: Color,
    bubble_fg: Color,
    border: Color,
    code_bg: Color,
    ok: Color,
    warn: Color,
    err: Color,
    hint: Color,
    chip_bg: Color,
}

const DEFAULT_DARK: TokenMap = TokenMap {
    bg: BLUISH_1000,
    surface: BLUISH_950,
    panel: BLUISH_900,
    fg: BLUISH_50,
    fg_secondary: BLUISH_300,
    fg_tertiary: BLUISH_500,
    caption: BLUISH_600,
    brand: DEEPSEEK_450,
    brand_soft: DEEPSEEK_400,
    bubble_bg: BLUISH_900,
    bubble_fg: BLUISH_75,
    border: BLUISH_850,
    code_bg: BLUISH_950,
    ok: GREEN_400,
    warn: AMBER_400,
    err: RED_400,
    hint: SLATE_400,
    chip_bg: BLUISH_850,
};

const DEFAULT_LIGHT: TokenMap = TokenMap {
    bg: BLUISH_00,
    surface: BLUISH_50,
    panel: BLUISH_60,
    fg: BLUISH_1000,
    fg_secondary: BLUISH_750,
    fg_tertiary: BLUISH_700,
    caption: BLUISH_400,
    brand: DEEPSEEK_500,
    brand_soft: DEEPSEEK_450,
    bubble_bg: BLUISH_75,
    bubble_fg: BLUISH_1000,
    border: BLUISH_200,
    code_bg: BLUISH_60,
    ok: GREEN_500,
    warn: AMBER_600,
    err: RED_600,
    hint: SLATE_600,
    chip_bg: BLUISH_100,
};

// --- catppuccin -----------------------------------------------------------

/// The four Catppuccin flavors, palette v1.8.0 (github.com/catppuccin/palette).
/// The role mapping is Textual's built-in `catppuccin-*` themes — the same four
/// names crow-cli's own TUI offers — so `bg`/`surface`/`panel`/`fg` and
/// `brand`/`brand_soft` are Textual's background/surface/panel/foreground and
/// primary/secondary verbatim: Mocha sits on `mantle`, the other three on
/// `base`, and Latte's stack is base → mantle → surface0. The two roles Textual
/// does not name come from the flavor's own scale — body text steps down
/// text → subtext1 → subtext0 → overlay0, and `border`/`chip_bg` are `surface2`
/// (Textual's Mocha `border-blurred`). `ok`/`warn`/`err`/`hint` are the
/// canonical green/yellow/red/teal; Textual's Mocha still carries the pre-1.0
/// hexes there, its other three flavors already agree.
const CATPPUCCIN_LATTE: TokenMap = TokenMap {
    bg: Color::Rgb(239, 241, 245),          // base #eff1f5
    surface: Color::Rgb(230, 233, 239),     // mantle #e6e9ef
    panel: Color::Rgb(204, 208, 218),       // surface0 #ccd0da
    fg: Color::Rgb(76, 79, 105),            // text #4c4f69
    fg_secondary: Color::Rgb(92, 95, 119),  // subtext1 #5c5f77
    fg_tertiary: Color::Rgb(108, 111, 133), // subtext0 #6c6f85
    caption: Color::Rgb(156, 160, 176),     // overlay0 #9ca0b0
    brand: Color::Rgb(136, 57, 239),        // mauve #8839ef
    brand_soft: Color::Rgb(220, 138, 120),  // rosewater #dc8a78
    bubble_bg: Color::Rgb(204, 208, 218),   // surface0 #ccd0da
    bubble_fg: Color::Rgb(76, 79, 105),     // text #4c4f69
    border: Color::Rgb(172, 176, 190),      // surface2 #acb0be
    code_bg: Color::Rgb(230, 233, 239),     // mantle #e6e9ef
    ok: Color::Rgb(64, 160, 43),            // green #40a02b
    warn: Color::Rgb(223, 142, 29),         // yellow #df8e1d
    err: Color::Rgb(210, 15, 57),           // red #d20f39
    hint: Color::Rgb(23, 146, 153),         // teal #179299
    chip_bg: Color::Rgb(172, 176, 190),     // surface2 #acb0be
};

const CATPPUCCIN_FRAPPE: TokenMap = TokenMap {
    bg: Color::Rgb(48, 52, 70),              // base #303446
    surface: Color::Rgb(65, 69, 89),         // surface0 #414559
    panel: Color::Rgb(81, 87, 109),          // surface1 #51576d
    fg: Color::Rgb(198, 208, 245),           // text #c6d0f5
    fg_secondary: Color::Rgb(181, 191, 226), // subtext1 #b5bfe2
    fg_tertiary: Color::Rgb(165, 173, 206),  // subtext0 #a5adce
    caption: Color::Rgb(115, 121, 148),      // overlay0 #737994
    brand: Color::Rgb(202, 158, 230),        // mauve #ca9ee6
    brand_soft: Color::Rgb(239, 159, 118),   // peach #ef9f76
    bubble_bg: Color::Rgb(81, 87, 109),      // surface1 #51576d
    bubble_fg: Color::Rgb(198, 208, 245),    // text #c6d0f5
    border: Color::Rgb(98, 104, 128),        // surface2 #626880
    code_bg: Color::Rgb(65, 69, 89),         // surface0 #414559
    ok: Color::Rgb(166, 209, 137),           // green #a6d189
    warn: Color::Rgb(229, 200, 144),         // yellow #e5c890
    err: Color::Rgb(231, 130, 132),          // red #e78284
    hint: Color::Rgb(129, 200, 190),         // teal #81c8be
    chip_bg: Color::Rgb(98, 104, 128),       // surface2 #626880
};

const CATPPUCCIN_MACCHIATO: TokenMap = TokenMap {
    bg: Color::Rgb(36, 39, 58),              // base #24273a
    surface: Color::Rgb(54, 58, 79),         // surface0 #363a4f
    panel: Color::Rgb(73, 77, 100),          // surface1 #494d64
    fg: Color::Rgb(202, 211, 245),           // text #cad3f5
    fg_secondary: Color::Rgb(184, 192, 224), // subtext1 #b8c0e0
    fg_tertiary: Color::Rgb(165, 173, 203),  // subtext0 #a5adcb
    caption: Color::Rgb(110, 115, 141),      // overlay0 #6e738d
    brand: Color::Rgb(198, 160, 246),        // mauve #c6a0f6
    brand_soft: Color::Rgb(245, 169, 127),   // peach #f5a97f
    bubble_bg: Color::Rgb(73, 77, 100),      // surface1 #494d64
    bubble_fg: Color::Rgb(202, 211, 245),    // text #cad3f5
    border: Color::Rgb(91, 96, 120),         // surface2 #5b6078
    code_bg: Color::Rgb(54, 58, 79),         // surface0 #363a4f
    ok: Color::Rgb(166, 218, 149),           // green #a6da95
    warn: Color::Rgb(238, 212, 159),         // yellow #eed49f
    err: Color::Rgb(237, 135, 150),          // red #ed8796
    hint: Color::Rgb(139, 213, 202),         // teal #8bd5ca
    chip_bg: Color::Rgb(91, 96, 120),        // surface2 #5b6078
};

const CATPPUCCIN_MOCHA: TokenMap = TokenMap {
    bg: Color::Rgb(24, 24, 37),              // mantle #181825
    surface: Color::Rgb(49, 50, 68),         // surface0 #313244
    panel: Color::Rgb(69, 71, 90),           // surface1 #45475a
    fg: Color::Rgb(205, 214, 244),           // text #cdd6f4
    fg_secondary: Color::Rgb(186, 194, 222), // subtext1 #bac2de
    fg_tertiary: Color::Rgb(166, 173, 200),  // subtext0 #a6adc8
    caption: Color::Rgb(108, 112, 134),      // overlay0 #6c7086
    brand: Color::Rgb(245, 194, 231),        // pink #f5c2e7
    brand_soft: Color::Rgb(203, 166, 247),   // mauve #cba6f7
    bubble_bg: Color::Rgb(69, 71, 90),       // surface1 #45475a
    bubble_fg: Color::Rgb(205, 214, 244),    // text #cdd6f4
    border: Color::Rgb(88, 91, 112),         // surface2 #585b70
    code_bg: Color::Rgb(49, 50, 68),         // surface0 #313244
    ok: Color::Rgb(166, 227, 161),           // green #a6e3a1
    warn: Color::Rgb(249, 226, 175),         // yellow #f9e2af
    err: Color::Rgb(243, 139, 168),          // red #f38ba8
    hint: Color::Rgb(148, 226, 213),         // teal #94e2d5
    chip_bg: Color::Rgb(88, 91, 112),        // surface2 #585b70
};

/// The ids [`PalettePack::builtin_packs`] carries, in picker order. What the
/// `/theme` menu calls a builtin rather than a theme plugin.
pub const BUILTIN_PALETTE_IDS: &[&str] = &[
    "default",
    "catppuccin-latte",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "catppuccin-mocha",
];

/// Why a protocol-0 palette was rejected. Wrong `protocol` is not an error:
/// the compositor ignores it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PaletteError(pub String);

impl std::fmt::Display for PaletteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// A named dark/light token pack. Built-in `default` plus registered Cordis packs.
#[derive(Clone, Debug, PartialEq)]
pub struct PalettePack {
    pub id: String,
    pub label: String,
    /// Dynamic Client Plugin that owns this selectable theme, when any.
    pub plugin_id: Option<String>,
    /// ACP-carried registry origin; Rust never infers this from plugin ids.
    pub source: String,
    /// Whether the owning Plugin is currently mounted.
    pub loaded: bool,
    /// Optional terminal background owned by this theme pack.
    pub background: Option<ThemeBackground>,
    /// The mode this pack is committed in, when it owns one: a built-in
    /// flavor is dark or light by nature (Catppuccin Latte *is* the light
    /// theme). `None` — every Plugin-registered pack, and `default` — keeps
    /// whichever mode is already in effect.
    pub preferred_mode: Option<Mode>,
    dark: TokenMap,
    light: TokenMap,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BackgroundSource {
    File { path: String },
    Data { base64: String },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackgroundFit {
    Cover,
    Contain,
    Stretch,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ThemeBackground {
    pub source: BackgroundSource,
    pub fit: BackgroundFit,
    pub anchor: (f64, f64),
    pub opacity: f64,
}

/// A parsed Cordis TUI theme update (`protocol` 0).
#[derive(Clone, Debug, PartialEq)]
pub struct PaletteNotification {
    pub pack: PalettePack,
    pub activate: bool,
}

impl PalettePack {
    pub fn builtin_default() -> Self {
        Self {
            id: "default".into(),
            label: "Default".into(),
            plugin_id: None,
            source: "static".into(),
            loaded: true,
            background: None,
            preferred_mode: None,
            dark: DEFAULT_DARK,
            light: DEFAULT_LIGHT,
        }
    }

    /// One built-in Catppuccin flavor. `dark` is the flavor itself — Latte
    /// pairs with Mocha — and `light` is always Latte, so ctrl+t still means
    /// something inside the family: Macchiato ↔ Latte.
    fn catppuccin(id: &str, label: &str, dark: TokenMap, preferred: Mode) -> Self {
        Self {
            id: id.into(),
            label: label.into(),
            plugin_id: None,
            source: "static".into(),
            loaded: true,
            background: None,
            preferred_mode: Some(preferred),
            dark,
            light: CATPPUCCIN_LATTE,
        }
    }

    /// Every pack the binary carries with no Plugin mounted: `default` plus
    /// the four Catppuccin flavors. `default` is always first and always
    /// present — the fallback for a persisted id this build does not know.
    /// The ids are [`BUILTIN_PALETTE_IDS`], in the same order.
    pub fn builtin_packs() -> Vec<Self> {
        vec![
            Self::builtin_default(),
            Self::catppuccin(
                "catppuccin-latte",
                "Catppuccin Latte",
                CATPPUCCIN_MOCHA,
                Mode::Light,
            ),
            Self::catppuccin(
                "catppuccin-frappe",
                "Catppuccin Frappé",
                CATPPUCCIN_FRAPPE,
                Mode::Dark,
            ),
            Self::catppuccin(
                "catppuccin-macchiato",
                "Catppuccin Macchiato",
                CATPPUCCIN_MACCHIATO,
                Mode::Dark,
            ),
            Self::catppuccin(
                "catppuccin-mocha",
                "Catppuccin Mocha",
                CATPPUCCIN_MOCHA,
                Mode::Dark,
            ),
        ]
    }

    /// Current-mode `Theme` for this pack. Toggle stays inside these maps.
    pub fn theme(&self, mode: Mode) -> Theme {
        Theme::from_maps(mode, self.dark, self.light)
    }

    /// Parse a palette object (`id` / `label` / complete `dark`+`light` maps).
    pub fn from_json(v: &Value) -> Result<Self, PaletteError> {
        let obj = v
            .as_object()
            .ok_or_else(|| PaletteError("palette must be an object".into()))?;
        for key in obj.keys() {
            if !matches!(
                key.as_str(),
                "id" | "label" | "dark" | "light" | "background"
            ) {
                return Err(PaletteError(format!("unknown palette field {key}")));
            }
        }
        let id = obj.get("id").and_then(Value::as_str).unwrap_or("");
        if id.is_empty() {
            return Err(PaletteError("palette id must be a non-empty string".into()));
        }
        let label = obj.get("label").and_then(Value::as_str).unwrap_or("");
        if label.is_empty() {
            return Err(PaletteError(
                "palette label must be a non-empty string".into(),
            ));
        }
        let dark = parse_token_map(obj.get("dark").unwrap_or(&Value::Null))?;
        let light = parse_token_map(obj.get("light").unwrap_or(&Value::Null))?;
        let background = obj.get("background").map(parse_background).transpose()?;
        Ok(Self {
            id: id.to_string(),
            label: label.to_string(),
            plugin_id: None,
            source: "static".into(),
            loaded: true,
            background,
            preferred_mode: None,
            dark,
            light,
        })
    }
}

fn parse_background(v: &Value) -> Result<ThemeBackground, PaletteError> {
    let obj = v
        .as_object()
        .ok_or_else(|| PaletteError("background must be an object".into()))?;
    for key in obj.keys() {
        if !matches!(key.as_str(), "source" | "fit" | "anchor" | "opacity") {
            return Err(PaletteError(format!("unknown background field {key}")));
        }
    }
    let source_obj = obj
        .get("source")
        .and_then(Value::as_object)
        .ok_or_else(|| PaletteError("background source must be an object".into()))?;
    let kind = source_obj.get("kind").and_then(Value::as_str).unwrap_or("");
    let source = match kind {
        "file" => {
            if source_obj
                .keys()
                .any(|key| !matches!(key.as_str(), "kind" | "path"))
            {
                return Err(PaletteError(
                    "file background only accepts kind and path".into(),
                ));
            }
            let path = source_obj.get("path").and_then(Value::as_str).unwrap_or("");
            if path.is_empty() || !std::path::Path::new(path).is_absolute() {
                return Err(PaletteError("background file path must be absolute".into()));
            }
            BackgroundSource::File {
                path: path.to_string(),
            }
        }
        "data" => {
            if source_obj
                .keys()
                .any(|key| !matches!(key.as_str(), "kind" | "mediaType" | "base64"))
            {
                return Err(PaletteError(
                    "data background only accepts kind, mediaType and base64".into(),
                ));
            }
            if source_obj.get("mediaType").and_then(Value::as_str) != Some("image/png") {
                return Err(PaletteError(
                    "background data mediaType must be image/png".into(),
                ));
            }
            let base64 = source_obj
                .get("base64")
                .and_then(Value::as_str)
                .unwrap_or("");
            if base64.is_empty() {
                return Err(PaletteError(
                    "background data base64 must be non-empty".into(),
                ));
            }
            BackgroundSource::Data {
                base64: base64.to_string(),
            }
        }
        _ => {
            return Err(PaletteError(
                "background source kind must be file or data".into(),
            ));
        }
    };
    let fit = match obj.get("fit").and_then(Value::as_str).unwrap_or("cover") {
        "cover" => BackgroundFit::Cover,
        "contain" => BackgroundFit::Contain,
        "stretch" => BackgroundFit::Stretch,
        _ => {
            return Err(PaletteError(
                "background fit must be cover, contain or stretch".into(),
            ));
        }
    };
    let anchor_obj = match obj.get("anchor") {
        Some(value) => value
            .as_object()
            .ok_or_else(|| PaletteError("background anchor must be an object".into()))?,
        None => {
            return Ok(ThemeBackground {
                source,
                fit,
                anchor: (0.5, 0.5),
                opacity: unit_field(obj.get("opacity"), 1.0, "background opacity")?,
            })
        }
    };
    for key in anchor_obj.keys() {
        if !matches!(key.as_str(), "x" | "y") {
            return Err(PaletteError(format!(
                "unknown background anchor field {key}"
            )));
        }
    }
    Ok(ThemeBackground {
        source,
        fit,
        anchor: (
            unit_field(anchor_obj.get("x"), 0.5, "background anchor x")?,
            unit_field(anchor_obj.get("y"), 0.5, "background anchor y")?,
        ),
        opacity: unit_field(obj.get("opacity"), 1.0, "background opacity")?,
    })
}

fn unit_field(value: Option<&Value>, default: f64, at: &str) -> Result<f64, PaletteError> {
    let number = value.and_then(Value::as_f64).unwrap_or(default);
    if !number.is_finite() || !(0.0..=1.0).contains(&number) {
        return Err(PaletteError(format!("{at} must be from 0 to 1")));
    }
    Ok(number)
}

/// Parse Cordis TUI theme-update params. `protocol != 0` (or missing) → `Ok(None)`.
pub fn parse_palette_notification(
    params: &Value,
) -> Result<Option<PaletteNotification>, PaletteError> {
    let protocol_ok = params.get("protocol").and_then(Value::as_u64) == Some(0);
    if !protocol_ok {
        return Ok(None);
    }
    let palette = params
        .get("palette")
        .ok_or_else(|| PaletteError("missing palette".into()))?;
    let mut pack = PalettePack::from_json(palette)?;
    pack.plugin_id = params
        .get("owner")
        .and_then(|owner| owner.get("pluginId"))
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
        .map(str::to_string);
    pack.source = match params.get("source").and_then(Value::as_str) {
        Some("dynamic") => "dynamic".into(),
        Some("static") | None => "static".into(),
        Some(source) => return Err(PaletteError(format!("invalid palette source {source}"))),
    };
    pack.loaded = params
        .get("loaded")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let activate = params
        .get("activate")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    Ok(Some(PaletteNotification { pack, activate }))
}

fn parse_token_map(v: &Value) -> Result<TokenMap, PaletteError> {
    let map = v
        .as_object()
        .ok_or_else(|| PaletteError("token map must be an object".into()))?;
    for key in map.keys() {
        if !TOKEN_NAMES.iter().any(|n| n == key) {
            return Err(PaletteError(format!("unknown token {key}")));
        }
    }
    Ok(TokenMap {
        bg: color_field(map, "bg")?,
        surface: color_field(map, "surface")?,
        panel: color_field(map, "panel")?,
        fg: color_field(map, "fg")?,
        fg_secondary: color_field(map, "fg_secondary")?,
        fg_tertiary: color_field(map, "fg_tertiary")?,
        caption: color_field(map, "caption")?,
        brand: color_field(map, "brand")?,
        brand_soft: color_field(map, "brand_soft")?,
        bubble_bg: color_field(map, "bubble_bg")?,
        bubble_fg: color_field(map, "bubble_fg")?,
        border: color_field(map, "border")?,
        code_bg: color_field(map, "code_bg")?,
        ok: color_field(map, "ok")?,
        warn: color_field(map, "warn")?,
        err: color_field(map, "err")?,
        hint: color_field(map, "hint")?,
        chip_bg: color_field(map, "chip_bg")?,
    })
}

fn color_field(map: &serde_json::Map<String, Value>, key: &str) -> Result<Color, PaletteError> {
    let Some(v) = map.get(key) else {
        return Err(PaletteError(format!("missing token {key}")));
    };
    let Some(s) = v.as_str() else {
        return Err(PaletteError(format!("token {key} must be #RRGGBB")));
    };
    parse_hex(s).ok_or_else(|| PaletteError(format!("token {key} must be #RRGGBB")))
}

fn parse_hex(s: &str) -> Option<Color> {
    let b = s.as_bytes();
    if b.len() != 7 || b[0] != b'#' {
        return None;
    }
    let r = u8::from_str_radix(std::str::from_utf8(&b[1..3]).ok()?, 16).ok()?;
    let g = u8::from_str_radix(std::str::from_utf8(&b[3..5]).ok()?, 16).ok()?;
    let bl = u8::from_str_radix(std::str::from_utf8(&b[5..7]).ok()?, 16).ok()?;
    Some(Color::Rgb(r, g, bl))
}

/// Semantic colors — a cold monochrome remap of the Web UI neutral-bluish
/// scale (the alias slot names are kept for reference).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Theme {
    pub mode: Mode,
    /// `--dsw-alias-bg-base`
    pub bg: Color,
    /// `--dsw-alias-bg-layer-1`
    #[allow(dead_code)]
    pub surface: Color,
    /// `--dsw-alias-bg-layer-2` (panels, tool cards)
    pub panel: Color,
    /// `--dsw-alias-label-primary`
    pub fg: Color,
    /// `--dsw-alias-label-secondary`
    pub fg_secondary: Color,
    /// `--dsw-alias-label-tertiary`
    pub fg_tertiary: Color,
    /// `--dsw-alias-label-caption`
    pub caption: Color,
    /// `--dsw-alias-brand-primary-new-color…` — the DeepSeek blue accent
    pub brand: Color,
    /// `--dsw-alias-state-business-primary`
    pub brand_soft: Color,
    /// `--dsw-specific-bubble` (user message bubble)
    pub bubble_bg: Color,
    /// text on the bubble
    pub bubble_fg: Color,
    /// borders (`--dsw-alias-border-l2/l3` approximated on the layer stack)
    pub border: Color,
    /// `--dsw-alias-markdown-code-block`
    pub code_bg: Color,
    /// `--dsw-alias-state-success-primary` / secondary
    pub ok: Color,
    /// `--dsw-alias-state-warn-primary` / label
    pub warn: Color,
    /// `--dsw-alias-state-error-primary`
    pub err: Color,
    /// Gray-blue hint text (tip banner, informational chips) — quieter
    /// than `brand_soft`, warmer than the neutral grays.
    pub hint: Color,
    /// selection/status chip background (picker row highlight)
    pub chip_bg: Color,
    dark: TokenMap,
    light: TokenMap,
}

impl Theme {
    fn from_maps(mode: Mode, dark: TokenMap, light: TokenMap) -> Self {
        let t = match mode {
            Mode::Dark => dark,
            Mode::Light => light,
        };
        Theme {
            mode,
            bg: t.bg,
            surface: t.surface,
            panel: t.panel,
            fg: t.fg,
            fg_secondary: t.fg_secondary,
            fg_tertiary: t.fg_tertiary,
            caption: t.caption,
            brand: t.brand,
            brand_soft: t.brand_soft,
            bubble_bg: t.bubble_bg,
            bubble_fg: t.bubble_fg,
            border: t.border,
            code_bg: t.code_bg,
            ok: t.ok,
            warn: t.warn,
            err: t.err,
            hint: t.hint,
            chip_bg: t.chip_bg,
            dark,
            light,
        }
    }

    pub fn dark() -> Self {
        Self::from_maps(Mode::Dark, DEFAULT_DARK, DEFAULT_LIGHT)
    }

    pub fn light() -> Self {
        Self::from_maps(Mode::Light, DEFAULT_DARK, DEFAULT_LIGHT)
    }

    pub fn toggled(&self) -> Self {
        match self.mode {
            Mode::Dark => Self::from_maps(Mode::Light, self.dark, self.light),
            Mode::Light => Self::from_maps(Mode::Dark, self.dark, self.light),
        }
    }

    /// Success accent used for finished tool glyphs and the idle dot.
    pub fn ok_soft(&self) -> Color {
        self.ok
    }

    /// Warn accent for chips, queue markers, and cautionary notices.
    pub fn warn_soft(&self) -> Color {
        self.warn
    }

    /// Whale banner vertical gradient stops (top → bottom), grayscale.
    pub fn whale_gradient(&self) -> (Color, Color) {
        match self.mode {
            Mode::Dark => (BLUISH_50, BLUISH_700),
            Mode::Light => (BLUISH_800, BLUISH_400),
        }
    }
}

/// Linear interpolation between two RGB colors, `t` in `[0, 1]`.
pub fn lerp(a: Color, b: Color, t: f32) -> Color {
    fn parts(c: Color) -> (f32, f32, f32) {
        match c {
            Color::Rgb(r, g, b) => (r as f32, g as f32, b as f32),
            _ => (255.0, 255.0, 255.0),
        }
    }
    let (ar, ag, ab) = parts(a);
    let (br, bg, bb) = parts(b);
    let t = t.clamp(0.0, 1.0);
    Color::Rgb(
        (ar + (br - ar) * t).round() as u8,
        (ag + (bg - ag) * t).round() as u8,
        (ab + (bb - ab) * t).round() as u8,
    )
}

#[cfg(test)]
#[path = "../tests/unit/theme__tests.rs"]
mod tests;
