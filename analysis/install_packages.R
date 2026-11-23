# Installs the R packages used by healthcare_report.qmd.
# Run once:  Rscript analysis/install_packages.R
packages <- c("DBI", "RSQLite", "dplyr", "tidyr", "ggplot2", "scales", "broom", "knitr", "rmarkdown")

# Use the repository already configured (e.g. binary packages in CI); otherwise CRAN
repos <- getOption("repos")
if (is.null(repos) || identical(unname(repos["CRAN"]), "@CRAN@")) repos <- "https://cloud.r-project.org"

missing <- setdiff(packages, rownames(installed.packages()))
if (length(missing) > 0) {
  install.packages(missing, repos = repos)
}
message("All packages installed: ", paste(packages, collapse = ", "))
