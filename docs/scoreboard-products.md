# Scoreboard, on product pages

Sluicer on [Zyte's product-extraction benchmark](https://github.com/scrapinghub/product-extraction-benchmark): 140 product pages as they
were served in 2021, scripts intact, with price, SKU and availability
labelled by hand. The benchmark ships the predictions of Zyte's and
Diffbot's paid extraction APIs and an open-source baseline built on
extruct and price-parser, and the evaluator that scores them. Sluicer's
predictions are added beside theirs and that evaluator runs unchanged, so
every rule below is Zyte's: a price matches as a decimal, several values
can be right, and a page with no availability counts as in stock.

Regenerated on 2026-09-24 from commit `ef9002c` by `uv run bench/products.py`, against the benchmark at `cba97d7a8d42`. Sluicer read the 140 pages in 1.2 s.

!!! warning "Read this before the numbers"
    Zyte and Diffbot are commercial services built on trained models,
    measured by Zyte in 2021 on pages it served them; Sluicer reads only
    what the page declares and runs no model. A price shown on the page
    and declared nowhere is a price Sluicer does not answer.

| attribute | system | F1 | precision | recall | pages labelled |
|---|---|---|---|---|---|
| price | **sluicer 0.4.1** | 0.750 ± 0.034 | 0.888 | 0.649 | 134 |
| price | extruct + price-parser | 0.685 ± 0.039 | 0.864 | 0.567 | 134 |
| price | Diffbot (paid API, 2021) | 0.824 ± 0.031 | 0.844 | 0.806 | 134 |
| price | Zyte Automatic Extraction (paid API, 2021) | 0.918 ± 0.023 | 0.918 | 0.918 | 134 |
| sku | **sluicer 0.4.1** | 0.541 ± 0.046 | 0.778 | 0.415 | 135 |
| sku | extruct + price-parser | 0.537 ± 0.045 | 0.786 | 0.407 | 135 |
| sku | Diffbot (paid API, 2021) | 0.765 ± 0.035 | 0.828 | 0.711 | 135 |
| sku | Zyte Automatic Extraction (paid API, 2021) | 0.841 ± 0.031 | 0.860 | 0.822 | 135 |
| availability | **sluicer 0.4.1** | 0.907 ± 0.026 | 0.907 | 0.907 | 140 |
| availability | extruct + price-parser | 0.626 ± 0.041 | 0.905 | 0.479 | 140 |
| availability | Diffbot (paid API, 2021) | 0.943 ± 0.020 | 0.943 | 0.943 | 140 |
| availability | Zyte Automatic Extraction (paid API, 2021) | 0.957 ± 0.018 | 0.957 | 0.957 | 140 |
| InStock | **sluicer 0.4.1** | 0.950 ± 0.014 | 0.954 | 0.947 | 131 |
| InStock | extruct + price-parser | 0.954 ± 0.014 | 0.954 | 0.954 | 131 |
| InStock | Diffbot (paid API, 2021) | 0.970 ± 0.011 | 0.956 | 0.985 | 131 |
| InStock | Zyte Automatic Extraction (paid API, 2021) | 0.977 ± 0.010 | 0.970 | 0.985 | 131 |
| OutOfStock | **sluicer 0.4.1** | 0.316 ± 0.140 | 0.300 | 0.333 | 9 |
| OutOfStock | extruct + price-parser | 0.333 ± 0.147 | 0.333 | 0.333 | 9 |
| OutOfStock | Diffbot (paid API, 2021) | 0.429 ± 0.175 | 0.600 | 0.333 | 9 |
| OutOfStock | Zyte Automatic Extraction (paid API, 2021) | 0.625 ± 0.154 | 0.714 | 0.556 | 9 |

The ± is the evaluator's bootstrap standard deviation over 1,000
resamples of the pages.

## Reading the errors

Every wrong price and every miss was read by hand, looking for rules
Sluicer had wrong rather than for rules that would fit these pages.

- **Labels that read a thousands point as a decimal one.** Three pages in
  Chile, Pakistan and Argentina show `24.990`, `23.450` and `2.449`, which
  are thousands in their currencies and are labelled as 24.99, 23.45 and
  2.449. Sluicer, reading the page's own markup, answers 24990, 23450 and
  2449, and is scored wrong on all three.
- **Pages that declare one price and show another.** A discounted price
  shown over the regular one the markup declares, an auction's current
  bid over its starting price. Zyte's own error analysis names the same
  cause for its system.
- **A label that accepts one spelling of an SKU on one Argos page and two
  on the other.** `924/9556` and `9249556` are both right on one; on the
  other only `466/7999` is, and Sluicer's declared `4667999` is scored
  wrong.
- **Pages that declare nothing.** Amazon's 20 pages declare no price in
  any vocabulary, and 15 of them are labelled with one: most of the 37
  prices Sluicer does not answer are on pages like these, shown and never
  declared. That is the difference between these numbers and the paid
  services', which read the visible page with trained models.

What the benchmark found in Sluicer, and is fixed: a microdata price
holding two numbers blocked the page's clean `product:price:amount`,
and a product declared once per colour, or beside related products,
was taken for a listing with no subject.
