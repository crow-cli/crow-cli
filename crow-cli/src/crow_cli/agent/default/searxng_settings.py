SEARXNG_SETTINGS_YML = """brand:
  docs_url: https://docs.searxng.org/
  issue_url: https://github.com/searxng/searxng/issues
  public_instances: https://searx.space
  wiki_url: https://github.com/searxng/searxng/wiki
categories_as_tabs:
  files: null
  general: null
  images: null
  it: null
  map: null
  music: null
  news: null
  science: null
  social media: null
  videos: null
default_doi_resolver: oadoi.org
doi_resolvers:
  doi.org: https://doi.org/
  oadoi.org: https://oadoi.org/
  sci-hub.ru: https://sci-hub.ru/
  sci-hub.se: https://sci-hub.se/
  sci-hub.st: https://sci-hub.st/
engines:
- disabled: true
  engine: 360search
  name: 360search
  shortcut: 360so
  timeout: 10.0
- disabled: true
  engine: 360search_videos
  name: 360search videos
  shortcut: 360sov
- disabled: true
  engine: 9gag
  name: 9gag
  shortcut: 9g
- disabled: true
  engine: acfun
  name: acfun
  shortcut: acf
- adobe_content_types:
  - photo
  - illustration
  - zip_vector
  - template
  - 3d
  - image
  adobe_order: relevance
  categories:
  - images
  disabled: true
  engine: adobe_stock
  name: adobe stock
  shortcut: asi
  timeout: 6
- adobe_content_types:
  - video
  adobe_order: relevance
  categories:
  - videos
  disabled: true
  engine: adobe_stock
  name: adobe stock video
  network: adobe stock
  shortcut: asv
  timeout: 6
- adobe_content_types:
  - audio
  adobe_order: relevance
  categories:
  - music
  disabled: true
  engine: adobe_stock
  name: adobe stock audio
  network: adobe stock
  shortcut: asa
  timeout: 6
- api_key: ''
  engine: astrophysics_data_system
  inactive: true
  name: astrophysics data system
  shortcut: ads
- disabled: true
  engine: alpinelinux
  name: alpine linux packages
  shortcut: alp
- base_url:
  - https://annas-archive.gl
  - https://annas-archive.vg
  - https://annas-archive.pk
  - https://annas-archive.gd
  disabled: true
  engine: annas_archive
  name: annas archive
  shortcut: aa
  timeout: 5
- disabled: true
  engine: ansa
  name: ansa
  shortcut: ans
- disabled: true
  engine: apkmirror
  name: apk mirror
  shortcut: apkm
  timeout: 4.0
- disabled: true
  engine: apple_app_store
  name: apple app store
  shortcut: aps
- categories: onions
  enable_http: true
  engine: ahmia
  name: ahmia
  shortcut: ah
  timeout: 20.0
- categories: it
  content_xpath: ./td[h5]/text()
  disabled: true
  engine: xpath
  first_page_num: 0
  name: anaconda
  paging: true
  results_xpath: //tbody/tr
  search_url: https://anaconda.org/search?q={query}&page={pageno}
  shortcut: conda
  timeout: 6.0
  title_xpath: ./td/h5
  url_xpath: ./td/h5/a[last()]/@href
- categories:
  - general
  disabled: true
  engine: aol
  name: aol
  search_type: search
  shortcut: aol
- categories:
  - images
  disabled: true
  engine: aol
  name: aol images
  search_type: image
  shortcut: aoli
- categories:
  - videos
  disabled: true
  engine: aol
  name: aol videos
  search_type: video
  shortcut: aolv
- engine: archlinux
  name: arch linux wiki
  shortcut: al
- base_url: https://wiki.nixos.org/
  categories:
  - it
  - software wikis
  disabled: true
  engine: mediawiki
  name: nixos wiki
  search_type: text
  shortcut: nixw
- engine: artic
  name: artic
  shortcut: arc
  timeout: 4.0
- categories: images
  disabled: true
  engine: artstation
  name: artstation
  shortcut: as
- engine: arxiv
  name: arxiv
  shortcut: arx
- disabled: true
  engine: ask
  name: ask
  shortcut: ask
- categories:
  - it
  - cloud
  engine: azure
  inactive: true
  name: azure
  shortcut: az
- categories: music
  engine: bandcamp
  name: bandcamp
  shortcut: bc
- baidu_category: general
  categories:
  - general
  disabled: true
  engine: baidu
  name: baidu
  shortcut: bd
- baidu_category: images
  categories:
  - images
  disabled: true
  engine: baidu
  name: baidu images
  shortcut: bdi
- baidu_category: it
  categories:
  - it
  disabled: true
  engine: baidu
  name: baidu kaifa
  shortcut: bdk
- categories:
  - general
  display_type:
  - infobox
  engine: wikipedia
  name: wikipedia
  shortcut: wp
- disabled: true
  engine: bilibili
  name: bilibili
  shortcut: bil
- disabled: true
  engine: bing
  name: bing
  shortcut: bi
- engine: bing_images
  name: bing images
  shortcut: bii
- engine: bing_news
  name: bing news
  shortcut: bin
- engine: bing_videos
  name: bing videos
  shortcut: biv
- disabled: true
  engine: bitchute
  name: bitchute
  shortcut: bit
- about:
    official_api_documentation: https://developer.atlassian.com/bitbucket
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://bitbucket.org/
    wikidata_id: Q2493781
  categories:
  - it
  - repos
  content_xpath: //article[@class="repo-summary"]/p
  disabled: true
  engine: xpath
  name: bitbucket
  paging: true
  search_url: https://bitbucket.org/repo/all/{pageno}?name={query}
  shortcut: bb
  timeout: 4.0
  title_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]
  url_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]/@href
- disabled: true
  engine: boardreader
  name: boardreader
  shortcut: boa
- disabled: true
  engine: bpb
  name: bpb
  shortcut: bpb
- disabled: true
  engine: btdigg
  name: btdigg
  shortcut: bt
- categories: images
  engine: openverse
  name: openverse
  shortcut: opv
- disabled: true
  engine: ccc_media
  name: media.ccc.de
  shortcut: c3tv
- disabled: true
  engine: cachy_os
  name: cachy os packages
  shortcut: cos
- engine: chefkoch
  name: chefkoch
  shortcut: chef
- categories:
  - news
  chinaso_category: news
  chinaso_news_source: all
  disabled: true
  engine: chinaso
  inactive: true
  name: chinaso news
  shortcut: chinaso
- categories:
  - images
  chinaso_category: images
  disabled: true
  engine: chinaso
  inactive: true
  name: chinaso images
  network: chinaso news
  shortcut: chinasoi
- categories:
  - videos
  chinaso_category: videos
  disabled: true
  engine: chinaso
  inactive: true
  name: chinaso videos
  network: chinaso news
  shortcut: chinasov
- cf_account_id: your_cf_accout_id
  cf_ai_api: your_cf_api
  cf_ai_gateway: your_cf_ai_gateway_name
  cf_ai_model: ai_model_name
  engine: cloudflareai
  inactive: true
  name: cloudflareai
  shortcut: cfai
  timeout: 30
- api_key: ''
  engine: core
  inactive: true
  name: core.ac.uk
  shortcut: cor
- disabled: true
  engine: crossref
  name: crossref
  shortcut: cr
  timeout: 30
- about:
    website: https://crowdview.ai/
  categories: general
  content_html_to_text: true
  content_query: snippet
  disabled: true
  engine: json_engine
  name: crowdview
  paging: false
  results_query: results
  search_url: https://crowdview-next-js.onrender.com/api/search-v3?query={query}
  shortcut: cv
  title_html_to_text: true
  title_query: title
  url_query: link
- categories: general
  disabled: true
  engine: yep
  name: yep
  search_type: web
  shortcut: yep
  timeout: 15
- categories: images
  disabled: true
  engine: yep
  name: yep images
  search_type: images
  shortcut: yepi
- categories: news
  disabled: true
  engine: yep
  name: yep news
  search_type: news
  shortcut: yepn
- engine: currency_convert
  name: currency
  shortcut: cc
- disabled: true
  engine: deezer
  name: deezer
  shortcut: dz
- disabled: true
  engine: destatis
  name: destatis
  shortcut: destat
- engine: deviantart
  name: deviantart
  shortcut: da
  timeout: 3.0
- engine: devicons
  name: devicons
  shortcut: di
  timeout: 3.0
- disabled: true
  engine: duckduckgo_definitions
  name: ddg definitions
  shortcut: ddd
  weight: 2
- categories:
  - it
  - packages
  engine: docker_hub
  name: docker hub
  shortcut: dh
- about:
    official_api_documentation: https://encyclosearch.org/docs/#/rest-api
    require_api_key: false
    results: JSON
    use_official_api: true
    website: https://encyclosearch.org
  categories: general
  content_query: Description
  disabled: true
  engine: json_engine
  name: encyclosearch
  paging: true
  results_query: Results
  search_url: https://encyclosearch.org/encyclosphere/search?q={query}&page={pageno}&resultsPerPage=15
  shortcut: es
  title_query: Title
  url_query: SourceURL
- about:
    official_api_documentation: null
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://www.erowid.org/
    wikidata_id: Q1430691
  categories: []
  content_xpath: //dl[@class="results-list"]/dd[@class="result-details"]
  disabled: true
  engine: xpath
  first_page_num: 0
  name: erowid
  page_size: 30
  paging: true
  search_url: https://www.erowid.org/search.php?q={query}&s={pageno}
  shortcut: ew
  title_xpath: //dl[@class="results-list"]/dt[@class="result-title"]/a/text()
  url_xpath: //dl[@class="results-list"]/dt[@class="result-title"]/a/@href
- engine: elasticsearch
  inactive: true
  name: elasticsearch
  query_type: match
  shortcut: els
- categories:
  - general
  display_type:
  - infobox
  engine: wikidata
  name: wikidata
  shortcut: wd
  timeout: 3.0
  weight: 2
- engine: duckduckgo
  name: duckduckgo
  shortcut: ddg
- categories:
  - images
  ddg_category: images
  engine: duckduckgo_extra
  name: duckduckgo images
  shortcut: ddi
- categories:
  - videos
  ddg_category: videos
  engine: duckduckgo_extra
  name: duckduckgo videos
  shortcut: ddv
- categories:
  - news
  ddg_category: news
  engine: duckduckgo_extra
  name: duckduckgo news
  shortcut: ddn
- disabled: true
  engine: duckduckgo_weather
  name: duckduckgo weather
  shortcut: ddw
- disabled: true
  engine: apple_maps
  name: apple maps
  shortcut: apm
  timeout: 5.0
- disabled: true
  engine: emojipedia
  name: emojipedia
  shortcut: em
  timeout: 4.0
- disabled: true
  engine: tineye
  name: tineye
  shortcut: tin
  timeout: 9.0
- about:
    official_api_documentation: null
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://www.etymonline.com/
    wikidata_id: Q1188617
  categories:
  - dictionaries
  content_xpath: //section[contains(@class, "word__defination")]
  engine: xpath
  first_page_num: 1
  name: etymonline
  paging: true
  search_url: https://etymonline.com/search?page={pageno}&q={query}
  shortcut: et
  title_xpath: //a[contains(@class, "word__name--")]
  url_xpath: //a[contains(@class, "word__name--")]/@href
- base_url: https://www.ebay.com
  engine: ebay
  inactive: true
  name: ebay
  shortcut: eb
  timeout: 5
- disabled: true
  engine: www1x
  name: 1x
  shortcut: 1x
  timeout: 3.0
- disabled: true
  engine: fdroid
  name: fdroid
  shortcut: fd
- disabled: true
  engine: findthatmeme
  name: findthatmeme
  shortcut: ftm
- categories: images
  engine: flickr_noapi
  name: flickr
  shortcut: fl
- categories: images
  engine: flickr
  inactive: true
  name: flickr_api
  shortcut: fla
- about:
    website: https://directory.fsf.org/
    wikidata_id: Q2470288
  base_url: https://directory.fsf.org/
  categories:
  - it
  - software wikis
  disabled: true
  engine: mediawiki
  name: free software directory
  search_type: title
  shortcut: fsd
  timeout: 5.0
- engine: freesound
  inactive: true
  name: freesound
  shortcut: fnd
  timeout: 15.0
- disabled: true
  engine: frinkiac
  name: frinkiac
  shortcut: frk
- about:
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://fynd.bot
  categories: general
  content_xpath: .//div[contains(@class, "description")]
  disabled: true
  engine: xpath
  first_page_num: 0
  name: fynd
  page_size: 10
  paging: true
  results_xpath: //div[contains(@class, "result-item")]
  safe_search_map:
    0: '&safe=0'
    1: '&safe=1'
    2: '&safe=1'
  safesearch: true
  search_url: https://fynd.bot/?search={query}&offset={pageno}{safe_search}
  shortcut: fynd
  thumbnail_xpath: .//img[contains(@class, "preview-img")]/@src
  title_xpath: .//div[contains(@class, "title-line")]
  url_xpath: .//a/@href
- disabled: true
  engine: fyyd
  name: fyyd
  shortcut: fy
  timeout: 8.0
- disabled: true
  engine: geizhals
  name: geizhals
  shortcut: geiz
- engine: genius
  name: genius
  shortcut: gen
- api_path: api.php
  base_url: https://wiki.gentoo.org/
  categories:
  - it
  - software wikis
  engine: mediawiki
  name: gentoo
  search_type: text
  shortcut: ge
  timeout: 10
- about:
    website: https://gitlab.com/
    wikidata_id: Q16639197
  base_url: https://gitlab.com
  disabled: true
  engine: gitlab
  name: gitlab
  shortcut: gl
- engine: github
  name: github
  shortcut: gh
- engine: github_code
  ghc_auth:
    token: token
    type: none
  ghc_highlight_matching_lines: true
  ghc_strip_new_lines: true
  ghc_strip_whitespace: false
  inactive: true
  name: github code
  shortcut: ghc
  timeout: 10.0
- base_url: https://codeberg.org
  disabled: true
  engine: gitea
  name: codeberg
  shortcut: cb
- base_url: https://gitea.com
  disabled: true
  engine: gitea
  name: gitea.com
  shortcut: gitea
- disabled: true
  engine: gmx
  name: gmx
  shortcut: gmx
- disabled: true
  engine: goodreads
  name: goodreads
  shortcut: good
  timeout: 4.0
- engine: google
  name: google
  shortcut: go
- engine: google_images
  name: google images
  shortcut: goi
- engine: google_news
  name: google news
  shortcut: gon
- engine: google_videos
  name: google videos
  shortcut: gov
- engine: google_scholar
  name: google scholar
  shortcut: gos
- categories:
  - files
  - apps
  disabled: true
  engine: google_play
  name: google play apps
  play_categ: apps
  shortcut: gpa
- categories: videos
  disabled: true
  engine: google_play
  name: google play movies
  play_categ: movies
  shortcut: gpm
- disabled: true
  engine: grokipedia
  inactive: true
  name: grokipedia
  shortcut: gp
- disabled: true
  engine: material_icons
  name: material icons
  shortcut: mi
- about:
    official_api_documentation: https://habr.com/en/docs/help/api/
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://habr.com/
    wikidata_id: Q4494434
  categories: it
  content_xpath: .//div[contains(@class, "article-formatted-body")]
  disabled: true
  engine: xpath
  name: habrahabr
  paging: true
  results_xpath: //article[contains(@class, "tm-articles-list__item")]
  search_url: https://habr.com/en/search/page{pageno}/?q={query}
  shortcut: habr
  timeout: 4.0
  title_xpath: .//a[@class="tm-title__link"]
  url_xpath: .//a[@class="tm-title__link"]/@href
- disabled: true
  engine: hackernews
  name: hackernews
  shortcut: hn
- disabled: true
  engine: hex
  name: hex
  page_size: 10
  shortcut: hex
  sort_criteria: recent_downloads
- disabled: true
  engine: crates
  name: crates.io
  shortcut: crates
  timeout: 6.0
- about:
    official_api_documentation: https://hackage.haskell.org/api
    require_api_key: false
    results: JSON
    use_official_api: false
    website: https://hoogle.haskell.org/
    wikidata_id: Q34010
  categories:
  - it
  - packages
  content_xpath: .//div[@class="from"]
  engine: xpath
  name: hoogle
  page_size: 20
  results_xpath: //div[@class="result"]
  search_url: https://hoogle.haskell.org/?hoogle={query}
  shortcut: ho
  title_xpath: .//div[@class="ans"]//a
  url_xpath: .//div[@class="ans"]//a/@href
- disabled: true
  engine: il_post
  name: il post
  shortcut: pst
- disabled: true
  engine: huggingface
  name: huggingface
  shortcut: hf
- disabled: true
  engine: huggingface
  huggingface_endpoint: datasets
  name: huggingface datasets
  shortcut: hfd
- disabled: true
  engine: huggingface
  huggingface_endpoint: spaces
  name: huggingface spaces
  shortcut: hfs
- disabled: true
  engine: imdb
  name: imdb
  shortcut: imdb
  timeout: 6.0
- disabled: true
  engine: imgur
  name: imgur
  shortcut: img
- disabled: true
  engine: ina
  name: ina
  shortcut: in
  timeout: 6.0
- disabled: true
  engine: ipernity
  name: ipernity
  shortcut: ip
- disabled: true
  engine: iqiyi
  name: iqiyi
  shortcut: iq
- disabled: true
  engine: jisho
  name: jisho
  shortcut: js
  timeout: 3.0
- categories:
  - general
  - web
  engine: karmasearch
  name: karmasearch
  search_type: web
  shortcut: ka
- categories:
  - images
  - web
  engine: karmasearch
  name: karmasearch images
  paging: false
  search_type: images
  shortcut: kai
- categories:
  - general
  - web
  engine: karmasearch
  name: karmasearch videos
  search_type: videos
  shortcut: kav
- categories:
  - news
  - web
  engine: karmasearch
  name: karmasearch news
  search_type: news
  shortcut: kan
- base_url:
  - https://kickasstorrents.to
  - https://kickasstorrents.cr
  - https://kickasstorrent.cr
  - https://kickass.sx
  - https://kat.am
  engine: kickass
  name: kickass
  shortcut: kc
  timeout: 4.0
- engine: lemmy
  lemmy_type: Communities
  name: lemmy communities
  shortcut: leco
- engine: lemmy
  lemmy_type: Users
  name: lemmy users
  network: lemmy communities
  shortcut: leus
- engine: lemmy
  lemmy_type: Posts
  name: lemmy posts
  network: lemmy communities
  shortcut: lepo
- engine: lemmy
  lemmy_type: Comments
  name: lemmy comments
  network: lemmy communities
  shortcut: lecom
- about:
    official_api_documentation: null
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://libgen.fun/
    wikidata_id: Q22017206
  categories: files
  content_xpath: //td/a[1][contains(@href,"=author")]/text()
  disabled: true
  engine: xpath
  name: library genesis
  search_url: https://libgen.rs/search.php?req={query}
  shortcut: lg
  timeout: 7.0
  title_xpath: //a[contains(@href,"book/")]/text()[1]
  url_xpath: //a[contains(@href,"book/index.php?md5")]/@href
- disabled: true
  engine: zlibrary
  inactive: true
  name: z-library
  shortcut: zlib
  timeout: 7.0
- categories: images
  disabled: true
  engine: loc
  name: library of congress
  shortcut: loc
- base_url:
  - https://libretranslate.com/translate
  engine: libretranslate
  inactive: true
  name: libretranslate
  shortcut: lt
- engine: lingva
  name: lingva
  shortcut: lv
  timeout: 6.0
- about:
    official_api_documentation: null
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://lobste.rs/
    wikidata_id: Q60762874
  categories: it
  content_xpath: .//a[@class="domain"]
  disabled: true
  engine: xpath
  name: lobste.rs
  results_xpath: //li[contains(@class, "story")]
  search_url: https://lobste.rs/search?q={query}&what=stories&order=relevance
  shortcut: lo
  timeout: 5.0
  title_xpath: .//a[@class="u-url"]
  url_xpath: .//a[@class="u-url"]/@href
- engine: lucide
  name: lucide
  shortcut: luc
  timeout: 3.0
- disabled: true
  engine: marginalia
  inactive: true
  name: marginalia
  shortcut: mar
- base_url: https://mastodon.social
  engine: mastodon
  mastodon_type: accounts
  name: mastodon users
  shortcut: mau
- base_url: https://mastodon.social
  engine: mastodon
  mastodon_type: hashtags
  name: mastodon hashtags
  shortcut: mah
- about:
    official_api_documentation: null
    require_api_key: false
    results: JSON
    use_official_api: false
    website: https://developer.mozilla.org
    wikidata_id: Q3273508
  categories:
  - it
  content_query: summary
  engine: json_engine
  name: mdn
  paging: true
  results_query: documents
  search_url: https://developer.mozilla.org/api/v1/search?q={query}&page={pageno}
  shortcut: mdn
  title_query: title
  url_prefix: https://developer.mozilla.org
  url_query: mdn_url
- disabled: true
  engine: metacpan
  name: metacpan
  number_of_results: 20
  shortcut: cpan
- disabled: true
  engine: microsoft_learn
  name: microsoft learn
  shortcut: msl
- engine: mixcloud
  name: mixcloud
  shortcut: mc
- base_url:
  - https://mozhi.aryak.me
  - https://translate.bus-hit.me
  - https://nyc1.mz.ggtyler.dev
  disabled: true
  engine: mozhi
  name: mozhi
  shortcut: mz
  timeout: 4.0
- disabled: true
  engine: mwmbl
  name: mwmbl
  shortcut: mwm
- disabled: true
  engine: niconico
  name: niconico
  shortcut: nico
- disabled: true
  engine: npm
  name: npm
  shortcut: npm
  timeout: 5.0
- disabled: true
  engine: nyaa
  name: nyaa
  shortcut: nt
- about:
    official_api_documentation: https://www.mankier.com/api
    require_api_key: false
    results: JSON
    use_official_api: true
    website: https://www.mankier.com/
  categories: it
  content_query: description
  engine: json_engine
  name: mankier
  results_query: results
  search_url: https://www.mankier.com/api/v2/mans/?q={query}
  shortcut: man
  title_query: name
  url_query: url
- disabled: true
  engine: odysee
  name: odysee
  shortcut: od
- disabled: true
  engine: ollama
  name: ollama
  shortcut: ollama
- about:
    official_api_documentation: https://api.openaire.eu/
    require_api_key: false
    results: JSON
    use_official_api: false
    website: https://www.openaire.eu/
    wikidata_id: Q25106053
  categories: science
  content_html_to_text: true
  content_query: metadata/oaf:entity/oaf:result/description/$
  engine: json_engine
  name: openairedatasets
  paging: true
  results_query: response/results/result
  search_url: https://api.openaire.eu/search/datasets?format=json&page={pageno}&size=10&title={query}
  shortcut: oad
  timeout: 5.0
  title_query: metadata/oaf:entity/oaf:result/title/$
  url_query: metadata/oaf:entity/oaf:result/children/instance/webresource/url/$
- about:
    official_api_documentation: https://api.openaire.eu/
    require_api_key: false
    results: JSON
    use_official_api: false
    website: https://www.openaire.eu/
    wikidata_id: Q25106053
  categories: science
  content_html_to_text: true
  content_query: metadata/oaf:entity/oaf:result/description/$
  engine: json_engine
  name: openairepublications
  paging: true
  results_query: response/results/result
  search_url: https://api.openaire.eu/search/publications?format=json&page={pageno}&size=10&title={query}
  shortcut: oap
  timeout: 5.0
  title_query: metadata/oaf:entity/oaf:result/title/$
  url_query: metadata/oaf:entity/oaf:result/children/instance/webresource/url/$
- disabled: true
  engine: openalex
  name: openalex
  shortcut: oa
  timeout: 5.0
- disabled: true
  engine: openclipart
  inactive: true
  name: openclipart
  shortcut: ocl
  timeout: 30
- disabled: true
  engine: openlibrary
  name: openlibrary
  shortcut: ol
  timeout: 10
- disabled: true
  engine: open_meteo
  name: openmeteo
  shortcut: om
- engine: openstreetmap
  name: openstreetmap
  shortcut: osm
- about:
    official_api_documentation: null
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://openrepos.net/
    wikidata_id: null
  categories: files
  content_xpath: //li[@class="search-result"]//div[@class="search-snippet-info"]//p[@class="search-snippet"]
  disabled: true
  engine: xpath
  name: openrepos
  paging: true
  search_url: https://openrepos.net/search/node/{query}?page={pageno}
  shortcut: or
  timeout: 4.0
  title_xpath: //li[@class="search-result"]//h3[@class="title"]/a
  url_xpath: //li[@class="search-result"]//h3[@class="title"]/a/@href
- about:
    official_api_documentation: https://packagist.org/apidoc
    require_api_key: false
    results: JSON
    use_official_api: true
    website: https://packagist.org
    wikidata_id: Q108311377
  categories:
  - it
  - packages
  content_query: description
  disabled: true
  engine: json_engine
  name: packagist
  paging: true
  results_query: results
  search_url: https://packagist.org/search.json?q={query}&page={pageno}
  shortcut: pack
  timeout: 5.0
  title_query: name
  url_query: url
- engine: pdbe
  name: pdbe
  shortcut: pdb
- engine: pexels
  name: pexels
  shortcut: pe
- engine: photon
  name: photon
  shortcut: ph
- engine: pinterest
  name: pinterest
  shortcut: pin
- backend_url:
  - https://pipedapi.ducks.party
  - https://api.piped.private.coffee
  categories: videos
  engine: piped
  frontend_url: https://srv.piped.video
  inactive: true
  name: piped
  piped_filter: videos
  shortcut: ppd
  timeout: 3.0
- categories: music
  engine: piped
  inactive: true
  name: piped.music
  network: piped
  piped_filter: music_songs
  shortcut: ppdm
  timeout: 3.0
- engine: piratebay
  name: piratebay
  shortcut: tpb
  timeout: 3.0
  url: https://thepiratebay.org/
- categories: images
  disabled: true
  engine: pixabay
  name: pixabay images
  pixabay_type: images
  shortcut: pixi
- categories: videos
  disabled: true
  engine: pixabay
  name: pixabay videos
  pixabay_type: videos
  shortcut: pixv
- disabled: true
  engine: pixiv
  inactive: true
  name: pixiv
  pixiv_image_proxies:
  - https://pximg.example.org
  remove_ai_images: false
  shortcut: pv
- engine: podcastindex
  name: podcastindex
  shortcut: podcast
- categories:
  - general
  - web
  disabled: true
  engine: presearch
  name: presearch
  search_type: search
  shortcut: ps
  timeout: 4.0
- categories:
  - images
  - web
  disabled: true
  engine: presearch
  name: presearch images
  network: presearch
  search_type: images
  shortcut: psimg
  timeout: 4.0
- categories:
  - general
  - web
  disabled: true
  engine: presearch
  name: presearch videos
  network: presearch
  search_type: videos
  shortcut: psvid
  timeout: 4.0
- categories:
  - news
  - web
  disabled: true
  engine: presearch
  name: presearch news
  network: presearch
  search_type: news
  shortcut: psnews
  timeout: 4.0
- about:
    official_api_documentation: https://pub.dev/help/api
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://pub.dev/
  categories:
  - packages
  - it
  content_xpath: ./div/div/div[contains(@class,"packages-description")]/span
  disabled: true
  engine: xpath
  first_page_num: 1
  name: pub.dev
  paging: true
  results_xpath: //div[contains(@class,"packages-item")]
  search_url: https://pub.dev/packages?q={query}&page={pageno}
  shortcut: pd
  timeout: 3.0
  title_xpath: ./div/h3/a
  url_xpath: ./div/h3/a/@href
- disabled: true
  engine: public_domain_image_archive
  name: public domain image archive
  shortcut: pdia
- engine: pubmed
  name: pubmed
  shortcut: pub
- engine: pypi
  name: pypi
  shortcut: pypi
- categories:
  - general
  disabled: true
  engine: quark
  name: quark
  quark_category: general
  shortcut: qk
- categories:
  - images
  disabled: true
  engine: quark
  name: quark images
  quark_category: images
  shortcut: qki
- categories:
  - general
  - web
  disabled: true
  engine: qwant
  name: qwant
  qwant_categ: web
  shortcut: qw
- categories: news
  engine: qwant
  name: qwant news
  network: qwant
  qwant_categ: news
  shortcut: qwn
- categories:
  - images
  - web
  engine: qwant
  name: qwant images
  network: qwant
  qwant_categ: images
  shortcut: qwi
- categories:
  - videos
  - web
  engine: qwant
  name: qwant videos
  network: qwant
  qwant_categ: videos
  shortcut: qwv
- engine: radio_browser
  name: radio browser
  shortcut: rb
- disabled: true
  engine: reddit
  name: reddit
  page_size: 25
  shortcut: re
- engine: reuters
  name: reuters
  shortcut: reu
- disabled: true
  engine: rottentomatoes
  name: rottentomatoes
  shortcut: rt
- about:
    website: https://searchmysite.net
  categories: general
  content_xpath: ./p[@id='result-hightlight']
  disabled: true
  engine: xpath
  name: searchmysite
  paging: true
  results_xpath: //div[contains(@class,'search-result')]
  search_url: https://searchmysite.net/search/?q={query}&page={pageno}
  shortcut: sms
  title_xpath: .//span[contains(@class,'result-title-txt')]/text()
  url_xpath: .//a[contains(@class,'result-link')]/@href
- disabled: true
  engine: selfhst
  name: selfhst icons
  shortcut: si
- engine: sepiasearch
  name: sepiasearch
  shortcut: sep
- disabled: true
  engine: sogou
  name: sogou
  shortcut: sogou
- disabled: true
  engine: sogou_images
  name: sogou images
  shortcut: sogoui
- disabled: true
  engine: sogou_videos
  name: sogou videos
  shortcut: sogouv
- disabled: true
  engine: sogou_wechat
  name: sogou wechat
  shortcut: sogouw
- engine: soundcloud
  name: soundcloud
  shortcut: sc
- api_site: stackoverflow
  categories:
  - it
  - q&a
  engine: stackexchange
  name: stackoverflow
  shortcut: st
- api_site: askubuntu
  categories:
  - it
  - q&a
  engine: stackexchange
  name: askubuntu
  shortcut: ubuntu
- api_site: superuser
  categories:
  - it
  - q&a
  engine: stackexchange
  name: superuser
  shortcut: su
- base_url: https://discuss.python.org
  categories:
  - it
  - q&a
  disabled: true
  engine: discourse
  name: discuss.python
  shortcut: dpy
- base_url: https://caddy.community
  categories:
  - it
  - q&a
  disabled: true
  engine: discourse
  name: caddy.community
  shortcut: caddy
- base_url: https://discourse.pi-hole.net
  categories:
  - it
  - q&a
  disabled: true
  engine: discourse
  name: pi-hole.community
  shortcut: pi
- engine: semantic_scholar
  name: semantic scholar
  shortcut: se
- api_key: ''
  engine: springer
  inactive: true
  name: springer nature
  shortcut: springer
  timeout: 5
- categories:
  - general
  - web
  engine: startpage
  name: startpage
  shortcut: sp
  startpage_categ: web
- categories:
  - news
  - web
  engine: startpage
  name: startpage news
  shortcut: spn
  startpage_categ: news
- categories:
  - images
  - web
  engine: startpage
  name: startpage images
  shortcut: spi
  startpage_categ: images
- disabled: true
  engine: steam
  name: steam
  shortcut: stm
- disabled: true
  engine: tokyotoshokan
  name: tokyotoshokan
  shortcut: tt
  timeout: 6.0
- base_url:
  - https://solidtorrents.to
  - https://bitsearch.to
  engine: solidtorrents
  name: solidtorrents
  shortcut: solid
  timeout: 4.0
- disabled: true
  engine: tagesschau
  name: tagesschau
  shortcut: ts
  use_source_url: true
- categories: movies
  content_xpath: .//div[contains(@class,"overview")]
  disabled: true
  engine: xpath
  name: tmdb
  paging: true
  results_xpath: //div[contains(@class,"movie") or contains(@class,"tv")]//div[contains(@class,"card")]
  search_url: https://www.themoviedb.org/search?page={pageno}&query={query}
  shortcut: tm
  thumbnail_xpath: .//img/@src
  title_xpath: .//div[contains(@class,"title")]//h2
  url_xpath: .//div[contains(@class,"poster")]/a/@href
- categories: onions
  content_xpath: ./td[2]/small
  enable_http: true
  engine: xpath
  name: torch
  paging: true
  results_xpath: //table//tr
  search_url: http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega?P={query}&DEFAULTOP=and
  shortcut: tch
  title_xpath: ./td[2]/b
  url_xpath: ./td[2]/a
- engine: torznab
  inactive: true
  name: Torznab EZTV
  shortcut: eztv
  show_magnet_links: true
  show_torrent_files: false
  torznab_categories:
  - 2000
  - 5000
- engine: unsplash
  name: unsplash
  shortcut: us
- categories: general
  disabled: true
  engine: yandex
  name: yandex
  search_type: web
  shortcut: yd
- categories: images
  disabled: true
  engine: yandex
  name: yandex images
  network: yandex
  search_type: images
  shortcut: ydi
- disabled: true
  engine: yandex_music
  name: yandex music
  network: yandex
  shortcut: ydm
- disabled: true
  engine: yahoo
  name: yahoo
  shortcut: yh
- engine: yahoo_news
  name: yahoo news
  shortcut: yhn
- engine: youtube_noapi
  name: youtube
  shortcut: yt
- engine: youtube_api
  inactive: true
  name: youtube_api
  shortcut: yta
- engine: dailymotion
  name: dailymotion
  shortcut: dm
- engine: vimeo
  name: vimeo
  shortcut: vm
- about:
    website: https://wiby.me/
  categories:
  - general
  - web
  content_query: Snippet
  disabled: true
  engine: json_engine
  name: wiby
  paging: true
  search_url: https://wiby.me/json/?q={query}&p={pageno}
  shortcut: wib
  title_query: Title
  url_query: URL
- about:
    website: https://www.wikibooks.org/
    wikidata_id: Q367
  base_url: https://{language}.wikibooks.org/
  categories:
  - general
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikibooks
  search_type: text
  shortcut: wb
  weight: 0.5
- about:
    website: https://www.wikinews.org/
    wikidata_id: Q964
  base_url: https://{language}.wikinews.org/
  categories:
  - news
  - wikimedia
  engine: mediawiki
  name: wikinews
  search_type: text
  shortcut: wn
  srsort: create_timestamp_desc
- about:
    website: https://www.wikiquote.org/
    wikidata_id: Q369
  base_url: https://{language}.wikiquote.org/
  categories:
  - general
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikiquote
  search_type: text
  shortcut: wq
  weight: 0.5
- about:
    website: https://www.wikisource.org/
    wikidata_id: Q263
  base_url: https://{language}.wikisource.org/
  categories:
  - general
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikisource
  search_type: text
  shortcut: ws
  weight: 0.5
- about:
    website: https://species.wikimedia.org/
    wikidata_id: Q13679
  base_url: https://species.wikimedia.org/
  categories:
  - general
  - science
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikispecies
  search_type: text
  shortcut: wsp
- about:
    website: https://www.wiktionary.org/
    wikidata_id: Q151
  base_url: https://{language}.wiktionary.org/
  categories:
  - dictionaries
  - wikimedia
  engine: mediawiki
  name: wiktionary
  search_type: text
  shortcut: wt
- about:
    website: https://www.wikiversity.org/
    wikidata_id: Q370
  base_url: https://{language}.wikiversity.org/
  categories:
  - general
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikiversity
  search_type: text
  shortcut: wv
  weight: 0.5
- about:
    website: https://www.wikivoyage.org/
    wikidata_id: Q373
  base_url: https://{language}.wikivoyage.org/
  categories:
  - general
  - wikimedia
  disabled: true
  engine: mediawiki
  name: wikivoyage
  search_type: text
  shortcut: wy
  weight: 0.5
- categories: images
  engine: wikicommons
  name: wikicommons.images
  shortcut: wci
  wc_search_type: image
- categories: videos
  engine: wikicommons
  name: wikicommons.videos
  shortcut: wcv
  wc_search_type: video
- categories: music
  engine: wikicommons
  name: wikicommons.audio
  shortcut: wca
  wc_search_type: audio
- categories: files
  engine: wikicommons
  name: wikicommons.files
  shortcut: wcf
  wc_search_type: file
- categories: general
  disabled: true
  engine: wolframalpha_noapi
  name: wolframalpha
  shortcut: wa
  timeout: 6.0
- categories: general
  engine: wolframalpha_api
  inactive: true
  name: wolframalpha_api
  shortcut: waa
  timeout: 6.0
- engine: dictzone
  name: dictzone
  shortcut: dc
- engine: translated
  name: mymemory translated
  shortcut: tl
  timeout: 5.0
- disabled: true
  engine: 1337x
  name: 1337x
  shortcut: 1337x
- disabled: true
  engine: duden
  name: duden
  shortcut: du
- disabled: true
  engine: seznam
  name: seznam
  shortcut: szn
- engine: deepl
  inactive: true
  name: deepl
  shortcut: dpl
  timeout: 5.0
- categories:
  - general
  - web
  disabled: true
  engine: mojeek
  name: mojeek
  shortcut: mjk
- categories:
  - images
  - web
  disabled: true
  engine: mojeek
  name: mojeek images
  paging: false
  search_type: images
  shortcut: mjkimg
- categories:
  - news
  - web
  disabled: true
  engine: mojeek
  name: mojeek news
  paging: false
  search_type: news
  shortcut: mjknews
- disabled: true
  engine: moviepilot
  name: moviepilot
  shortcut: mp
- disabled: true
  engine: nvd
  name: national vulnerability database
  shortcut: nvd
- categories:
  - general
  - web
  disabled: true
  engine: naver
  name: naver
  shortcut: nvr
- categories:
  - images
  disabled: true
  engine: naver
  name: naver images
  naver_category: images
  shortcut: nvri
- categories:
  - news
  disabled: true
  engine: naver
  name: naver news
  naver_category: news
  shortcut: nvrn
- categories:
  - videos
  disabled: true
  engine: naver
  name: naver videos
  naver_category: videos
  shortcut: nvrv
- about:
    official_api_documentation: https://guides.rubygems.org/rubygems-org-api/
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://rubygems.org/
    wikidata_id: Q1853420
  categories:
  - it
  - packages
  content_xpath: ./span/p
  disabled: true
  engine: xpath
  first_page_num: 1
  name: rubygems
  paging: true
  results_xpath: /html/body/main/div/a[@class="gems__gem"]
  search_url: https://rubygems.org/search?page={pageno}&query={query}
  shortcut: rbg
  suggestion_xpath: /html/body/main/div/div[@class="search__suggestions"]/p/a
  title_xpath: ./span/h2
  url_xpath: ./@href
- categories: videos
  disabled: true
  engine: peertube
  name: peertube
  paging: true
  shortcut: ptb
  timeout: 6.0
- disabled: true
  engine: mediathekviewweb
  name: mediathekviewweb
  shortcut: mvw
- base_url:
  - https://yacy.searchlab.eu
  categories: general
  disabled: true
  engine: yacy
  name: yacy
  search_mode: global
  search_type: text
  shortcut: ya
  timeout: 5.0
- categories: images
  disabled: true
  engine: yacy
  name: yacy images
  network: yacy
  search_type: image
  shortcut: yai
  timeout: 5.0
- base_url: https://rumble.com/
  categories: videos
  disabled: true
  engine: rumble
  name: rumble
  paging: true
  shortcut: ru
- disabled: true
  engine: repology
  inactive: true
  name: repology
  shortcut: rep
- engine: wordnik
  name: wordnik
  shortcut: wnik
  timeout: 5.0
- about:
    language: de
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://www.woxikon.de/
    wikidata_id: null
  categories:
  - dictionaries
  content_xpath: //div[@class="synonyms-list-group"]
  disabled: true
  engine: xpath
  name: woxikon.de synonyme
  no_result_for_http_status:
  - 404
  search_url: https://synonyme.woxikon.de/synonyme/{query}.php
  shortcut: woxi
  timeout: 5.0
  title_xpath: //div[@class="upper-synonyms"]/a
  url_xpath: //div[@class="upper-synonyms"]/a/@href
- disabled: true
  engine: svgrepo
  name: svgrepo
  shortcut: svg
  timeout: 10.0
- engine: tootfinder
  name: tootfinder
  shortcut: toot
- disabled: true
  engine: uxwing
  name: uxwing
  shortcut: ux
- disabled: true
  engine: voidlinux
  name: voidlinux
  shortcut: void
- engine: wallhaven
  inactive: true
  name: wallhaven
  shortcut: wh
- about:
    language: fr
    require_api_key: false
    results: HTML
    use_official_api: false
    website: https://wikimini.org/
    wikidata_id: Q3568032
  categories: general
  content_xpath: //li/div[@class="searchresult"]
  disabled: true
  engine: xpath
  name: wikimini
  search_url: https://fr.wikimini.org/w/index.php?search={query}&title=Sp%C3%A9cial%3ASearch&fulltext=Search
  shortcut: wkmn
  title_xpath: //li//div[@class="mw-search-result-heading"]/a
  url_xpath: //li/div[@class="mw-search-result-heading"]/a/@href
- engine: wttr
  name: wttr.in
  shortcut: wttr
  timeout: 9.0
- api_key: ''
  engine: braveapi
  inactive: true
  name: braveapi
- brave_category: search
  categories:
  - general
  - web
  engine: brave
  name: brave
  paging: true
  shortcut: br
  time_range_support: true
- brave_category: images
  categories:
  - images
  - web
  engine: brave
  name: brave.images
  network: brave
  shortcut: brimg
- brave_category: videos
  categories:
  - videos
  - web
  engine: brave
  name: brave.videos
  network: brave
  shortcut: brvid
- brave_category: news
  categories: news
  engine: brave
  name: brave.news
  network: brave
  shortcut: brnews
- disabled: true
  engine: lib_rs
  name: lib.rs
  shortcut: lrs
- disabled: true
  engine: sourcehut
  name: sourcehut
  shortcut: srht
- engine: bt4g
  name: bt4g
  shortcut: bt4g
- disabled: true
  engine: pkg_go_dev
  name: pkg.go.dev
  shortcut: pgo
- disabled: true
  engine: senscritique
  name: senscritique
  shortcut: scr
  timeout: 4.0
- about:
    website: https://minecraft.wiki/
    wikidata_id: Q105533483
  api_path: api.php
  base_url: https://minecraft.wiki/
  categories:
  - software wikis
  disabled: true
  engine: mediawiki
  name: minecraft wiki
  search_type: text
  shortcut: mcw
general:
  contact_url: false
  debug: false
  donation_url: false
  enable_metrics: true
  instance_name: SearXNG
  open_metrics: ''
  privacypolicy_url: false
outgoing:
  enable_http2: true
  pool_connections: 100
  pool_maxsize: 20
  request_timeout: 3.0
  useragent_suffix: ''
plugins:
  searx.plugins.ahmia_filter.SXNGPlugin:
    active: true
  searx.plugins.calculator.SXNGPlugin:
    active: true
  searx.plugins.hash_plugin.SXNGPlugin:
    active: true
  searx.plugins.hostnames.SXNGPlugin:
    active: true
  searx.plugins.infinite_scroll.SXNGPlugin:
    active: false
  searx.plugins.oa_doi_rewrite.SXNGPlugin:
    active: false
  searx.plugins.self_info.SXNGPlugin:
    active: true
  searx.plugins.time_zone.SXNGPlugin:
    active: true
  searx.plugins.tor_check.SXNGPlugin:
    active: false
  searx.plugins.tracker_url_remover.SXNGPlugin:
    active: true
  searx.plugins.unit_converter.SXNGPlugin:
    active: true
search:
  autocomplete: ''
  autocomplete_min: 4
  ban_time_on_fail: 5
  default_lang: auto
  favicon_resolver: ''
  formats:
  - html
  - json
  max_ban_time_on_fail: 120
  safe_search: 0
  suspended_times:
    SearxEngineAccessDenied: 180
    SearxEngineCaptcha: 3600
    SearxEngineTooManyRequests: 180
    cf_SearxEngineAccessDenied: 86400
    cf_SearxEngineCaptcha: 1296000
    recaptcha_SearxEngineCaptcha: 604800
server:
  base_url: false
  bind_address: 127.0.0.1
  default_http_headers:
    Referrer-Policy: no-referrer
    X-Content-Type-Options: nosniff
    X-Download-Options: noopen
    X-Robots-Tag: noindex, nofollow
  http_protocol_version: '1.0'
  image_proxy: false
  limiter: false
  method: POST
  port: 8888
  public_instance: false
  secret_key: tNVkGrRUXcYeHZpM449HubebophLt0Xf
ui:
  center_alignment: false
  default_locale: ''
  default_theme: simple
  hotkeys: default
  query_in_title: false
  search_on_category_select: true
  static_path: ''
  templates_path: ''
  theme_args:
    simple_style: auto
  url_formatting: pretty
valkey:
  url: false
"""
