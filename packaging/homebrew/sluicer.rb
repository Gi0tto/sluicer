class Sluicer < Formula
  include Language::Python::Virtualenv

  desc "Turn a web page into structured data with no model in the loop"
  homepage "https://github.com/Gi0tto/sluicer"
  url "https://files.pythonhosted.org/packages/85/14/d6066423f0437a7fb78b712c76504810d0543c3bf0a19f4fea69503ee50a/sluicer-0.8.0.tar.gz"
  sha256 "c44a84dd15900a3eebcb79e4b32167e9178ee4afae2fdd53ff3309f87686ba54"
  license all_of: ["MIT", "CC-BY-SA-3.0", "Unicode-3.0"]
  head "https://github.com/Gi0tto/sluicer.git", branch: "main"

  depends_on "python@3.14"

  uses_from_macos "libxml2", since: :ventura
  uses_from_macos "libxslt"

  resource "click" do
    url "https://files.pythonhosted.org/packages/c7/0e/7fa0ef50764b67090eca4114772a2abf8b6148198475e54c660b97caeee6/click-8.5.0.tar.gz"
    sha256 "ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34"
  end

  resource "cssselect" do
    url "https://files.pythonhosted.org/packages/8e/5a/6d6fcf922709391fac986f0a03ad4546f4f45b94d10aeb6c1ee041599993/cssselect-1.5.0.tar.gz"
    sha256 "3cbe82dd7acbee9ba9e5723b5f9e4749826912f1fb31cd7f92aabed5fde15b15"
  end

  resource "lxml" do
    url "https://files.pythonhosted.org/packages/23/ad/28ecd7cb894d172f3c9c80a075eeeb2017ac62e3632cee05a5f9493547eb/lxml-6.1.3.tar.gz"
    sha256 "45222d94ddd511536f3b2f7d9deae3b2339b4ce0f075f1ca25703b07cad9dd21"
  end

  resource "protego" do
    url "https://files.pythonhosted.org/packages/7a/d9/5026b9e75db1172f02441a84eaf42efb199b4cea14dda7651a620d1acd40/protego-0.7.0.tar.gz"
    sha256 "2c032d9736a1f4f0c4318f3558353ae34da5cd038f1a5e064ded7548df315e5a"
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
