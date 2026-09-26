class Sluicer < Formula
  include Language::Python::Virtualenv

  desc "Turn a web page into structured data with no model in the loop"
  homepage "https://github.com/Gi0tto/sluicer"
  url "https://files.pythonhosted.org/packages/source/s/sluicer/sluicer-0.9.1.tar.gz"
  # PLACEHOLDER: sluicer 0.9.1 has no sdist yet. Run
  # packaging/recipes.py again once it is on PyPI.
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license all_of: ["MIT", "CC-BY-SA-3.0", "Unicode-3.0"]
  head "https://github.com/Gi0tto/sluicer.git", branch: "main"

  depends_on "python@3.14"

  uses_from_macos "libxml2", since: :ventura
  uses_from_macos "libxslt"

  resource "babel" do
    url "https://files.pythonhosted.org/packages/7d/b2/51899539b6ceeeb420d40ed3cd4b7a40519404f9baf3d4ac99dc413a834b/babel-2.18.0.tar.gz"
    sha256 "b80b99a14bd085fcacfa15c9165f651fbb3406e66cc603abf11c5750937c992d"
  end

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz"
    sha256 "741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55"
  end

  resource "charset-normalizer" do
    url "https://files.pythonhosted.org/packages/e5/3f/143b048436775b0f76ac3eec145c019e8173ccc2885c8f20319b996d5e83/charset_normalizer-3.5.1.tar.gz"
    sha256 "6117b84ea48435e5356dc737f5121485c30920ba43375fa7b434fd753df0eac3"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/c7/0e/7fa0ef50764b67090eca4114772a2abf8b6148198475e54c660b97caeee6/click-8.5.0.tar.gz"
    sha256 "ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34"
  end

  resource "courlan" do
    url "https://files.pythonhosted.org/packages/bb/16/2a771612ee0b3acaa95ac21cc7e8a3319e815d6360f8ffc5987d1ce28499/courlan-1.4.0.tar.gz"
    sha256 "fbbac7b7fcde2195ea08e707609503c81cf39c891e8d26cdb1fed4585782d63d"
  end

  resource "cssselect" do
    url "https://files.pythonhosted.org/packages/8e/5a/6d6fcf922709391fac986f0a03ad4546f4f45b94d10aeb6c1ee041599993/cssselect-1.5.0.tar.gz"
    sha256 "3cbe82dd7acbee9ba9e5723b5f9e4749826912f1fb31cd7f92aabed5fde15b15"
  end

  resource "dateparser" do
    url "https://files.pythonhosted.org/packages/c7/5d/bd21ba1519b6b1e222b29878301d2e1fb928e890dc7d085fa4222ac5671b/dateparser-1.4.3.tar.gz"
    sha256 "bab8c43a746266e68142f4926e69438ce551441aa88e54e78bb6410bf3ee7000"
  end

  resource "htmldate" do
    url "https://files.pythonhosted.org/packages/ad/1f/e7cf83e23d7b68105de8b874a8b36ba23b450d6f71388583e4ca3ce475ca/htmldate-1.10.0.tar.gz"
    sha256 "a38df10772ab5d7dbb11896e3f6a852a8491fb1b0965465bc174e23fc2baae58"
  end

  resource "justext" do
    url "https://files.pythonhosted.org/packages/49/f3/45890c1b314f0d04e19c1c83d534e611513150939a7cf039664d9ab1e649/justext-3.0.2.tar.gz"
    sha256 "13496a450c44c4cd5b5a75a5efcd9996066d2a189794ea99a49949685a0beb05"
  end

  resource "lxml" do
    url "https://files.pythonhosted.org/packages/23/ad/28ecd7cb894d172f3c9c80a075eeeb2017ac62e3632cee05a5f9493547eb/lxml-6.1.3.tar.gz"
    sha256 "45222d94ddd511536f3b2f7d9deae3b2339b4ce0f075f1ca25703b07cad9dd21"
  end

  resource "lxml-html-clean" do
    url "https://files.pythonhosted.org/packages/0a/63/195dfdde380a84df309e3bccf4384b034b745dba43426886f7ae623b4fba/lxml_html_clean-0.4.5.tar.gz"
    sha256 "e2a4c7d5beedd17cd7b484d848a0571e54baa239a4f9df5546e3acba7f990560"
  end

  resource "protego" do
    url "https://files.pythonhosted.org/packages/7a/d9/5026b9e75db1172f02441a84eaf42efb199b4cea14dda7651a620d1acd40/protego-0.7.0.tar.gz"
    sha256 "2c032d9736a1f4f0c4318f3558353ae34da5cd038f1a5e064ded7548df315e5a"
  end

  resource "python-dateutil" do
    url "https://files.pythonhosted.org/packages/66/c0/0c8b6ad9f17a802ee498c46e004a0eb49bc148f2fd230864601a86dcf6db/python-dateutil-2.9.0.post0.tar.gz"
    sha256 "37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3"
  end

  resource "pytz" do
    url "https://files.pythonhosted.org/packages/fb/48/fb042503b6ca6cd271261dc559fd6432f7d8c713153e9ec5c591af4dfc1c/pytz-2026.3.post1.tar.gz"
    sha256 "2211d3fcf9a797d3405cac96ac7f61d80e6a644f72a3309607282fe8a2010c5d"
  end

  resource "regex" do
    url "https://files.pythonhosted.org/packages/b9/5c/f403115361de25809e8f785686ec7096e30fef73be9ae35aa51da4e80abb/regex-2026.9.10.tar.gz"
    sha256 "1e321e2c84f0e52c457f5ea5944f796d6e8e09cb99738ea98dcc1bfe402a128d"
  end

  resource "six" do
    url "https://files.pythonhosted.org/packages/94/e7/b2c673351809dca68a0e064b6af791aa332cf192da575fd474ed7d6f16a2/six-1.17.0.tar.gz"
    sha256 "ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81"
  end

  resource "tld" do
    url "https://files.pythonhosted.org/packages/5c/5d/76b4383ac4e5b5e254e50c09807b3e13820bed6d6c11cd540264988d6802/tld-0.13.2.tar.gz"
    sha256 "d983fa92b9d717400742fca844e29d5e18271079c7bcfabf66d01b39b4a14345"
  end

  resource "trafilatura" do
    url "https://files.pythonhosted.org/packages/a3/96/737133a93e73e967f9c888e6cfb1f2c31b2083d27263edb19fd65a9aca02/trafilatura-2.2.0.tar.gz"
    sha256 "8c2cabb84066465228d03183fb698ce0b1245b81c58140b8ae0de57fddf3aae7"
  end

  resource "tzlocal" do
    url "https://files.pythonhosted.org/packages/81/5b/879b2f932adfa7a053c360d50bc896c977fa6426109185f7c12ebdd0cb9d/tzlocal-5.4.4.tar.gz"
    sha256 "8dbb8660838688a7b6ba4fed31d18dedf842afb4d47ca050d6d891c2c15f3be4"
  end

  resource "urllib3" do
    url "https://files.pythonhosted.org/packages/e3/05/b17359e1cefb4f909b5e40b1b90a496d987258916dbbf88e842c729f510e/urllib3-2.8.0.tar.gz"
    sha256 "63bf2ead4c879426ebf22ef2a781eeb4aa3b4ae798a0435506f8687fd5bb9b63"
  end

  def install
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resources
    venv.pip_install buildpath
    # sluicer-mcp is the MCP server, which needs the mcp extra; this
    # formula installs the base package, so only sluicer is linked.
    bin.install_symlink libexec/"bin/sluicer"
    generate_completions_from_executable(bin/"sluicer", shell_parameter_format: :click)
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/sluicer --version")

    (testpath/"page.html").write <<~HTML
      <html><head><title>Brake pads</title>
      <script type="application/ld+json">
      {"@context": "https://schema.org", "@type": "Product", "name": "Brake pads",
       "offers": {"@type": "Offer", "price": "19.99", "priceCurrency": "EUR"}}
      </script></head><body></body></html>
    HTML
    output = JSON.parse(shell_output("#{bin}/sluicer extract #{testpath}/page.html"))
    assert_equal "19.99", output["summary"]["price"]["value"]
    assert_equal "jsonld", output["summary"]["price"]["source"]
  end
end
