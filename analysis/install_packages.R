# Installs the R packages used by healthcare_report.qmd.
# Run once:  Rscript analysis/install_packages.R
packages <- c("DBI", "RSQLite", "dplyr", "tidyr", "ggplot2", "scales", "broom", "knitr", "rmarkdown")
missing <- setdiff(packages, rownames(installed.packages()))
if (length(missing) > 0) {
  install.packages(missing, repos = "https://cloud.r-project.org")
}
message("All packages installed: ", paste(packages, collapse = ", "))
