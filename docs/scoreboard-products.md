# Scoreboard, on product pages

Sluicer on [Zyte's product-extraction benchmark](https://github.com/scrapinghub/product-extraction-benchmark): 140 product pages as they
were served in 2021, scripts intact, with price, SKU and availability
labelled by hand. The benchmark ships the predictions of Zyte's and
Diffbot's paid extraction APIs and an open-source baseline built on
extruct and price-parser, and the evaluator that scores them. Sluicer's
predictions are added beside theirs and that evaluator runs unchanged, so
every rule below is Zyte's: a price matches as a decimal, several values
can be right, and a page with no availability counts as in stock.

Regenerated on 2026-09-25 from commit `c51a9a3` by `uv run bench/products.py`, against the benchmark at `cba97d7a8d42`. Sluicer read the 140 pages in 1.1 s.

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`7876710`; `9548a35` added the SKU names the
    extruct baseline reads, to pass it), so this measures Sluicer on
    pages it was fitted to, not on pages it has never seen. Of the
    scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
    says which pages each rule was made on.

!!! warning "Read this before the numbers"
    Zyte and Diffbot are commercial services built on trained models,
    measured by Zyte in 2021 on pages it served them; Sluicer reads only
    what the page declares and runs no model. A price shown on the page
    and declared nowhere is a price Sluicer does not answer.

| attribute | system | F1 | precision | recall | pages labelled |
|---|---|---|---|---|---|
| price | **sluicer 0.7.1** | 0.750 ± 0.034 | 0.888 | 0.649 | 134 |
| price | extruct + price-parser | 0.685 ± 0.039 | 0.864 | 0.567 | 134 |
| price | Diffbot (paid API, 2021) | 0.824 ± 0.031 | 0.844 | 0.806 | 134 |
| price | Zyte Automatic Extraction (paid API, 2021) | 0.918 ± 0.023 | 0.918 | 0.918 | 134 |
| sku | **sluicer 0.7.1** | 0.541 ± 0.046 | 0.778 | 0.415 | 135 |
| sku | extruct + price-parser | 0.537 ± 0.045 | 0.786 | 0.407 | 135 |
| sku | Diffbot (paid API, 2021) | 0.765 ± 0.035 | 0.828 | 0.711 | 135 |
| sku | Zyte Automatic Extraction (paid API, 2021) | 0.841 ± 0.031 | 0.860 | 0.822 | 135 |
| availability | **sluicer 0.7.1** | 0.907 ± 0.026 | 0.907 | 0.907 | 140 |
| availability | extruct + price-parser | 0.626 ± 0.041 | 0.905 | 0.479 | 140 |
| availability | Diffbot (paid API, 2021) | 0.943 ± 0.020 | 0.943 | 0.943 | 140 |
| availability | Zyte Automatic Extraction (paid API, 2021) | 0.957 ± 0.018 | 0.957 | 0.957 | 140 |
| InStock | **sluicer 0.7.1** | 0.950 ± 0.014 | 0.954 | 0.947 | 131 |
| InStock | extruct + price-parser | 0.954 ± 0.014 | 0.954 | 0.954 | 131 |
| InStock | Diffbot (paid API, 2021) | 0.970 ± 0.011 | 0.956 | 0.985 | 131 |
| InStock | Zyte Automatic Extraction (paid API, 2021) | 0.977 ± 0.010 | 0.970 | 0.985 | 131 |
| OutOfStock | **sluicer 0.7.1** | 0.316 ± 0.140 | 0.300 | 0.333 | 9 |
| OutOfStock | extruct + price-parser | 0.333 ± 0.147 | 0.333 | 0.333 | 9 |
| OutOfStock | Diffbot (paid API, 2021) | 0.429 ± 0.175 | 0.600 | 0.333 | 9 |
| OutOfStock | Zyte Automatic Extraction (paid API, 2021) | 0.625 ± 0.154 | 0.714 | 0.556 | 9 |

The ± is the evaluator's bootstrap standard deviation over 1,000
resamples of the pages.

## Reading the errors

Each class below is counted from this run's answers and the labels.

- **Labels that read a thousands point as a decimal one.** On 3 pages -- paris.cl, olx.com.pk and stockcenter.com.ar -- Sluicer's price, read from the page's own markup, is a thousand
  times the label's: 24990 against 24.99, 23450 against 23.450 and 2449.00 against 2.449. Read by hand at 0.7.0, these are prices written with a thousands
  point, as in `24.990`, that the labels read as a decimal one.
- **Other wrong prices.** 7 more answered prices are accepted by no label.
  Read by hand at 0.7.0, they are pages that declare one price and show
  another: a discounted price shown over the regular one the markup
  declares, an auction's current bid over its starting price. Zyte's own
  error analysis names the same cause for its system.
- **SKUs.** 16 answered SKUs are accepted by no label. On 1 of them
  the label accepts the SKU as the page shows it and not as it declares
  it: `466/7999` and not `4667999` (argos.co.uk).
- **Prices not answered.** Sluicer answers no price on 37 of the 134
  pages labelled with one. On 37 of them no price reaches its summary
  -- 15 of them among Amazon's 20 pages -- and on
  0 the price declared does not read as one decimal. A price
  shown and never declared is what the paid services read off the
  visible page with trained models, and the difference between their
  numbers and these.

Rules made while reading these pages, before 0.7.0: a microdata price
holding two numbers no longer blocks the page's clean
`product:price:amount`, a product declared once per colour or beside
related products is no longer taken for a listing with no subject
(`7876710`), and an SKU is also read from `productID`, `og:sku` and
`product:sku`, as the extruct baseline reads it (`9548a35`).
