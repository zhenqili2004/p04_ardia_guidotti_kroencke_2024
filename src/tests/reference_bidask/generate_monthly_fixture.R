# Regenerate numeric oracles using unmodified pinned author functions.
# Run from repository root: Rscript src/tests/reference_bidask/generate_monthly_fixture.R
library(data.table)
setDTthreads(1)
root <- "src/tests/reference_bidask"
for (f in c("utils.R", "edge.R", "roll.R", "ar.R", "cs.R")) source(file.path(root,f))
args <- commandArgs(trailingOnly=TRUE)
input <- if(length(args)>=1) args[1] else file.path(root,"monthly_inputs.csv")
destination <- if(length(args)>=2) args[2] else file.path(root,"monthly_expected.csv")
x <- read.csv(input)
output <- lapply(split(x,x$case), function(d) {
  d <- d[order(d$position),]
  n <- nrow(d)
  data.frame(case=d$case[1],
    edge_signed=edge(d$open,d$high,d$low,d$close,sign=TRUE),
    roll_signed=tail(ROLL(d$close,n,TRUE,TRUE)$ROLL,1),
    ar_signed=tail(AR(d$high,d$low,d$close,n,"AR",TRUE,TRUE)$AR,1),
    cs_signed=tail(CS(d$high,d$low,d$close,n,"CS",TRUE,TRUE)$CS,1))
})
write.table(do.call(rbind,output),destination,
            sep=",",row.names=FALSE,na="NA",quote=FALSE)
