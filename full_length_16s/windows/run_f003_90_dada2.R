#!/usr/bin/env Rscript
# KIST F003 (90 biological samples) PacBio full-length 16S DADA2.
# This is native Windows R DADA2; it is not a QIIME 2 QZA run.
args=commandArgs(trailingOnly=TRUE)
if(length(args)<2L)stop("Usage: Rscript run_f003_90_dada2.R manifest_local.tsv output_dir [threads]")
manifest_path=normalizePath(args[1],mustWork=TRUE)
out=normalizePath(args[2],winslash="/",mustWork=FALSE)
threads=if(length(args)>2L)as.integer(args[3])else 6L
stopifnot(threads>=1L,threads<=8L)
lib=file.path(Sys.getenv("USERPROFILE"),"Documents","KIST16S_Local","Rlibrary")
.libPaths(c(lib,.libPaths()))
suppressPackageStartupMessages(library(dada2))
dir.create(out,recursive=TRUE,showWarnings=FALSE)
log_path=file.path(out,"pipeline.log")
logmsg=function(...) {
  m=paste0(format(Sys.time(),"%Y-%m-%d %H:%M:%S")," | ",paste0(...,collapse=""))
  cat(m,"\n");cat(m,"\n",file=log_path,append=TRUE)
  flush.console()
}
manifest=read.delim(manifest_path,sep="\t",check.names=FALSE,stringsAsFactors=FALSE,quote="")
stopifnot(nrow(manifest)==90L,!anyDuplicated(manifest[["sample-id"]]))
stopifnot(!any(grepl("^(PC|NC)($|__)",manifest[["sample-id"]])))
raw=normalizePath(manifest[["fastq"]],winslash="/",mustWork=TRUE)
names(raw)=manifest[["sample-id"]]
forward="AGRGTTYGATYMTGGCTCAG"; reverse="GYTACCTTGTTACGACTT"
logmsg("START 90 samples | R=",getRversion()," | dada2=",packageVersion("dada2"),
       " | threads=",threads," | forward=",forward," | reverse=",reverse)
logmsg("Windows: filterAndTrim uses serial execution; learnErrors/dada may use multithreading.")
tdir=file.path(out,"01_primer_trimmed")
fdir=file.path(out,"02_filtered")
cpdir=file.path(out,"checkpoints")
for(p in c(tdir,fdir,cpdir))dir.create(p,recursive=TRUE,showWarnings=FALSE)
trim=stats::setNames(file.path(tdir,paste0(names(raw),"_trim.fastq.gz")),names(raw))
filt=stats::setNames(file.path(fdir,paste0(names(raw),"_filtered.fastq.gz")),names(raw))
primer_counts=file.path(cpdir,"primer_counts.tsv")
if(file.exists(primer_counts)){
  pc=read.delim(primer_counts,stringsAsFactors=FALSE,check.names=FALSE)
}else{
  pc=data.frame(sample_id=character(),reads_in=integer(),reads_primer=integer(),stringsAsFactors=FALSE)
}
# Windows uses PSOCK workers: no fork/mclapply, with per-batch checkpoints.
completed=names(raw) %in% pc$sample_id & file.exists(trim) &
          !is.na(file.info(trim)$size) & file.info(trim)$size>0
pending=which(!completed)
if(length(pending)>0L){
  workers=min(4L,threads,length(pending))
  logmsg("PRIMER parallel Windows PSOCK workers=",workers,
         " remaining samples=",length(pending))
  cl=parallel::makePSOCKcluster(workers)
  tryCatch({
    parallel::clusterExport(cl,c("lib","raw","trim","forward","reverse"),
              envir=environment())
    parallel::clusterEvalQ(cl,{
      .libPaths(c(lib,.libPaths()))
      suppressPackageStartupMessages(library(dada2))
      NULL
    })
    batches=split(pending,ceiling(seq_along(pending)/workers))
    for(batch_no in seq_along(batches)){
      returned=parallel::parLapplyLB(cl,batches[[batch_no]],function(i){
        sid=names(raw)[i]
        result=removePrimers(raw[[sid]],trim[[sid]],primer.fwd=forward,
          primer.rev=dada2::rc(reverse),max.mismatch=2,
          allow.indels=FALSE,orient=TRUE,compress=TRUE,verbose=FALSE)
        data.frame(sample_id=sid,
          reads_in=as.integer(result[1,"reads.in"]),
          reads_primer=as.integer(result[1,"reads.out"]))
      })
      for(row in returned)pc=rbind(pc[pc$sample_id!=row$sample_id,,drop=FALSE],row)
      write.table(pc,primer_counts,sep="\t",row.names=FALSE,quote=FALSE)
      logmsg("PRIMER completed=",nrow(pc),"/",length(raw),
         " reads=",sum(pc$reads_primer),"/",sum(pc$reads_in))
    }
  },finally={
    parallel::stopCluster(cl)
  })
}
pc=pc[match(names(raw),pc$sample_id),,drop=FALSE]
stopifnot(all(!is.na(pc$reads_primer)))
filter_track_path=file.path(cpdir,"filter_tracking.rds")
if(file.exists(filter_track_path)&&all(file.exists(filt))){
  track=readRDS(filter_track_path)
  logmsg("Resume existing filter results")
}else{
  logmsg("FILTER begin 90 PacBio CCS samples, 1000-1600 bp, maxEE=2")
  track=filterAndTrim(unname(trim),unname(filt),minLen=1000,maxLen=1600,
         maxN=0,maxEE=2,truncQ=0,rm.phix=FALSE,
         multithread=FALSE,verbose=TRUE)
  rownames(track)=names(raw)
  saveRDS(track,filter_track_path)
  logmsg("FILTER completed total reads=",sum(track[,2]))
}
good=rownames(track)[track[,2]>0L]
if(length(good)<80L)stop("Less than 80 samples passed denoising input filter: ",length(good))
errpath=file.path(cpdir,"pacbio_error_model.rds")
if(file.exists(errpath)){
  err=readRDS(errpath);logmsg("Resume saved PacBio error model")
}else{
  logmsg("Learn PacBio error model from filtered reads")
  err=learnErrors(filt[good],nbases=1e8,errorEstimationFunction=PacBioErrfun,
                  multithread=threads,randomize=TRUE,verbose=TRUE)
  saveRDS(err,errpath)
  logmsg("Saved PacBio error model")
}
dereppath=file.path(cpdir,"derep.rds")
if(file.exists(dereppath)){
  dereps=readRDS(dereppath)
  logmsg("Resume derep")
}else{
  logmsg("Dereplicating 90 samples")
  dereps=derepFastq(filt[good],verbose=TRUE)
  names(dereps)=good
  saveRDS(dereps,dereppath)
}
dadapath=file.path(cpdir,"dada_inference.rds")
if(file.exists(dadapath)){
  denoised=readRDS(dadapath)
  logmsg("Resume DADA2 inference")
}else{
  logmsg("DADA inference: threads=",threads)
  denoised=dada(dereps,err=err,multithread=threads,verbose=TRUE)
  saveRDS(denoised,dadapath)
  logmsg("DADA inference finished")
}
seqtabpath=file.path(cpdir,"sequence_table_unfiltered.rds")
if(file.exists(seqtabpath)){
  seqtab=readRDS(seqtabpath)
}else{
  seqtab=makeSequenceTable(denoised)
  saveRDS(seqtab,seqtabpath)
}
chimpath=file.path(cpdir,"sequence_table_nochim.rds")
if(file.exists(chimpath)){
  nochim=readRDS(chimpath)
}else{
  logmsg("Chimera consensus removal")
  nochim=removeBimeraDenovo(seqtab,method="consensus",multithread=threads,
            minFoldParentOverAbundance=3.5,verbose=TRUE)
  saveRDS(nochim,chimpath)
}
logmsg("ASV FINAL SAMPLES=",nrow(nochim)," ASVs=",ncol(nochim),
       " retained reads=",sum(nochim))
# Preserve all 90 expected samples, adding zero-feature rows when filtering yielded zero reads.
full=matrix(0L,nrow=nrow(manifest),ncol=ncol(nochim),
            dimnames=list(manifest[["sample-id"]],colnames(nochim)))
full[rownames(nochim),]=nochim
asvseq=colnames(full)
asvid=sprintf("ASV%06d",seq_along(asvseq))
tableout=data.frame(ASV_ID=asvid,t(full),check.names=FALSE)
write.table(tableout,file.path(out,"feature-table.tsv"),sep="\t",
          row.names=FALSE,col.names=TRUE,quote=FALSE)
writeLines(as.vector(rbind(paste0(">",asvid),asvseq)),
           file.path(out,"ASV_sequences.fasta"),useBytes=TRUE)
write.table(data.frame(ASV_ID=asvid,Sequence=asvseq),
       file.path(out,"asv_sequence_map.tsv"),sep="\t",quote=FALSE,row.names=FALSE)
retained=rowSums(full)
denoised_reads=stats::setNames(vapply(denoised,dada2::getN,numeric(1)),names(denoised))
stats=data.frame(sample_id=names(raw),primer_reads=pc$reads_primer,
      raw_reads=pc$reads_in,filtered_reads=as.integer(track[names(raw),2]),
      denoised_reads=as.integer(denoised_reads[names(raw)]),
      nonchim_reads=as.integer(retained[names(raw)]))
write.table(stats,file.path(out,"denoising_stats.tsv"),
    sep="\t",quote=FALSE,row.names=FALSE)
alpha=data.frame(sample_id=rownames(full),
    total_reads=rowSums(full),
    observed_ASVs=rowSums(full>0),
    shannon=apply(full,1,function(v){p=v[v>0]/sum(v);if(length(p)==0)return(NA_real_);-sum(p*log(p))}),
    simpson=apply(full,1,function(v){p=v[v>0]/sum(v);if(length(p)==0)return(NA_real_);1-sum(p^2)}))
write.table(alpha,file.path(out,"alpha_diversity_unrarefied.tsv"),
    sep="\t",quote=FALSE,row.names=FALSE)
saveRDS(full,file.path(out,"asv_sample_matrix.rds"))
logmsg("SUCCESS: feature-table.tsv, ASV_sequences.fasta, denoising_stats.tsv, alpha_diversity_unrarefied.tsv")
