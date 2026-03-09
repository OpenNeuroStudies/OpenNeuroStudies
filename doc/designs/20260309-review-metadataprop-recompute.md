In doc/designs/20251226-hierarchical-stats-extraction.md we envisioned hierarchical metadata extraction so
we get efficient caching + metadata flow -- see "Consolidated flow" there 

But looking at what we have now:

    $> grep ds002843 studies*tsv
    studies.tsv:study-ds002843      Study dataset for ds002843      n/a     1.0.1   1.10.1  1.1.1   n/a     CC0     Yaroslav Halchenko      Sangil Lee      Joseph Kable    1       raw     0       166     1431    4       10      2630    290821  itc,rest,risk   293       290     78668149917     2559851481      46784733        217088  anat,dwi,fmap,func      n/a     n/a

but looking at that dataset:

    (git)smaug:~/proj/openneuro/OpenNeuroStudies[master]git
    $> head study-ds002843/sourcedata/sourcedata+subjects+sessions.tsv
    source_id       subject_id      session_id      bold_num        t1w_num t2w_num bold_size       t1w_size        bold_duration_total     bold_duration_mean      bold_voxels_total       bold_voxels_mean        datatypes
    ds002843        sub-dmp0005     ses-scan1       9       1       1       307148078       8324505 n/a     n/a     n/a     n/a     anat,fmap,func
    ds002843        sub-dmp0010     ses-scan1       9       1       1       309683322       8391702 n/a     n/a     n/a     n/a     anat,fmap,func
    ds002843        sub-dmp0010     ses-scan2       9       1       1       312875012       8377597 n/a     n/a     n/a     n/a     anat,fmap,func

we see n/a for bold_* columns whenever they are filled in in studies.tsv.

So somehwere we do not have workflow operating correctly:  it must process
exgtracts strictly in hierarchical fashion and thus higher level studies.tsv
must not be able to contain non-n/a values whenever underlying
sourcedata+subjects+sessions.tsv  has n/a's .  

TODOs:

- [ ] review specification under specs/ whether it reflrects this aspect cleanly
  and has specified ways to ensure/test correct operation.

- [ ] review implementation (and potentially git log) on how above situation has
  happened and whether we must fix the code or just retrigger computation if
  code was already fixed -- provide plan!

Then it relates to the idea was that we do not need to recompute those which
were not effected (according to git versions), e.g. if we computed stats
already and then we get updates to study-ds002843/sourcedata/ds002843 to only
sub-dmp0010/ses-scan1 folder -- we must re-extract metadata only for that
subject subfolder and not do full rescan of the dataset.

TODOs:

- [ ] review specification under specs/ whether it reflrects this aspect cleanly
  and has specified ways to ensure/test correct operation.

- [ ] review implementation on either such dependencies already being
  tracked correctly and aggregation is efficient. if not -- prepare plan on how to address.





