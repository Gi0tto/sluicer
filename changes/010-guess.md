### Fixed

- The summary's title kept the site's name after a separator whenever the page did not declare that name ("Personal Training - UT RecSports"), and took a business's name or a description written into `headline` over the title the page shows. Of the titles a page declares, the one its `<h1>` heading shows is now the title, cut where the heading ends; the answer is still the declared text, and with no such heading nothing changes.
