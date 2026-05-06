# Sample R script — open with TextView, press F5 to run via Rscript.

square <- function(x) {
  x * x
}

xs <- 1:6
ys <- sapply(xs, square)

cat("squares of", paste(xs, collapse = ", "), "=\n")
print(ys)

# Quick summary stats.
cat("\nMean:", mean(ys), "\n")
cat("Sum :", sum(ys), "\n")
