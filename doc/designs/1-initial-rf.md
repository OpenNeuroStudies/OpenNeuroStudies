# Current state:

Load @README.md and referenced there @doc/project_summary.md (paths are relative to the top directory, ../../ from here).

# The goals

## Structure overall OpenNeuroStudies as a "study" dataset itself with corresponding components

### sourcedata/

Those DataLad superdatasets will be the sources to operate on

- openfmri/ submodule leading to https://datasets.datalad.org/openfmri/.git

  - or may be better - just a spec (yaml file with top org, regex for
    repos to include) to traverse and list GitHub organization
    https://github.com/OpenNeuroDatasets 

- openneuro/ submodule leading to https://datasets.datalad.org/openneuro/.git
- openneuro-derivatives/ submodule leading to  https://github.com/OpenNeuroDerivatives/OpenNeuroDerivatives
- (later) cerebra-felix -- to point to collection under https://cerebra.fz-juelich.de/f.hoffstaedter/

  - similar to OpenNeuroDatasets above, may be here spec to point to that cerebra (which is an instance of 
    https://codeberg.org/matrss/forgejo-aneksajo)

- (later) registry.yaml -- spec to point to https://registry.datalad.org to
  potentially discover new derivatives to be included.

In the future we might need to extend to datasets coming from other
portals and sources.

Scripts should operate on them to 

- discover known datasets 
- get their urls from .gitmodules
- get their current state (commit hexsha) to be able to update as needed
- be able to fetch corresponding dataset_description.json and any other specific file
  without needing to clone an entire dataset (so using known URLs how to access a tree for github and forgejo)

### code/ 

that's where all the code should reside

#### code/containers

We might want submodule for https://github.com/repronim/containers to get
access to bids-validator container for consistency etc... but yet not sure if
needed or we just better use e.g.

   uvx bids-validator-deno@2.1.0 ...

to invoke it with a specific version


### study-{id}/

Subfolders per each study.
ATM it is just a subfolder, and we will keep it that way for now.

Later (add TODO for future refactorings) -- will need to become a separate git
repository to be hosted under https://github.com/OpenNeuroStudies/
organization, and linked here as git submodule.

### README.md

our description for the project

### CHANGES

Ideally we should do versioning, use 0. MAJOR as prefix and then .DATE and then .PATCH.
E.g. 0.20250918.0 for todays first release.  But we must not always release. Rather we should have a helper command (openneurostudies release [--newmajor])
which would

- figure out the next release for the same (or next if --newmajor) MAJOR by
  using the date, and then .PATCH (.0 if no prior release for the date, or
  increment by 1 to .1 and so on)
- use `claude` to produce a new CHANGES entry from prior tag using `git log` and following specification for CPAN CHANGES (https://metacpan.org/pod/CPAN::Changes::Spec) as BIDS mandates

### studies.tsv

The file summarizing information about studies:

- original authors (not the author of the study dataset)
- set of licenses of source and derivative datasets
- set of sourcedata BIDS versions and derivative data BIDS versions
- list of original source datasets from openneuro (most will have just 1, but some might more)
- list of derivatives available in the study
- TODO: figure out how to summarize state across derivatives... yet to think through

Script to produce such a summary should be indempotent and 

- extract data from underlying study
- be able to update/add for specific list of studies, not all at once (and delete if needed)
- produce/update studies.json file which would follow typical BIDS sidecar for .tsv files and describe the purpose of each column
  Consult https://bids-specification.readthedocs.io/en/stable/common-principles.html#tabular-files

## Populate and keep in "sync" each individual study-{} dataset



### dataset_description.json 

Should not be copied, and rather generated. With the Authors entry to come from

    git shortlog -sn

command, thus summarizing all contributors to the "study" dataset.

"Title" should come from the underlying `sourcedata/raw/dataset_description.json` but prefixed with "Study dataset for ".

"BIDSVersion" should be "1.10.1" or whatever other future version we would decide to work with later.

Populate "SourceDatasets" (ref in BIDS:
https://bids-specification.readthedocs.io/en/stable/glossary.html#objects.metadata.SourceDatasets)
with references to all datasets under sourcedata/ .

Generate "GeneratedBy" (ref in BIDS:
https://bids-specification.readthedocs.io/en/stable/glossary.html#objects.metadata.GeneratedBy)
with details about this code.

Populate "Funding" based on potentially present Funding in all included
subdatasets of the study (source or derivatives) and additional one (if
not already listed) for OpenNeuro NIH grant: "NIH #2R24MH117179-06".

Following fields should be copied *as is* from  `sourcedata/raw/dataset_description.json`

- ReferencesAndLinks
- License 
- Keywords
- Acknowledgements

If there are multiple source datasets, collate ReferencesAndLinks and Keywords
as a superset from all, and for License choose the most popular among those.
Acknowledgements also should be composition from all unique Acknowledgements (as a single string).

### sourcedata/

All linked as git submodules by using `datalad clone -d . ORIG_URL
sourcedata/<destination>`.  But that would require full cloning which takes
time and might require notable disk space.  It should be avoidable via looking
and reusing information within .gitmodules within corresponding superdataset,
like sourcedata/openneuro/ etc, and then duplicating it in our studies dataset using following workflow:

    # example parameters for submodule
    sub_url=https://github.com/OpenNeuroDatasets/ds000001
    sub_path=${sub_url##*/}
    sub_name=${sub_path///-}
    sub_hexsha=f8e27ac909e50b5b5e311f6be271f0b1757ebb7b

    mkdir "$sub_path"
    git config -f .gitmodules submodule."$sub_name".path "$sub_path"
    git config -f .gitmodules submodule."$sub_name".url "$sub_url"
    # here could be more
    git add .gitmodules
    # Add a gitlink pointing to the desired commit
    # Make sure the path does not already exist as a tracked file/directory.
    # Use the commit hex SHA from the submodule repo:
    git update-index --add --cacheinfo 160000,${sub_hexsha},"$sub_path"
    git commit -m "Added manually submodule '$sub_path'"

This way we could populate them very quickly without needing to clone at all.

#### incorporate older openfmri datasets (where available)

as `sourcedata/openfmri` 

DataLad datasets produced by datalad-crawler for older (pre bids) openfmri versions of openneuro datasets.

Those should be linked as git submodules into corresponding study datasets under study-{id}/sourcedata/openfmri .

#### incorporate ones from sourcedata/openneuro

As `sourcedata/raw`

See below a note though for studies based on "derivative" datasets in OpenNeuro with multiple SourceDatasets

### derivatives/

#### incorporate ones from sourcedata/openneuro-derivatives

#### incorporate derivatives already present in openneuro

Some datasets at OpenNeuro are derivative datasets of other datasets at OpenNeuro! we can determine using SourceDatasets field.
Here is e.g. what could be seen now.

    $> tools/find_attrs SourceDatasets -- ds*/dataset*json
    ds001769/dataset_description.json:
      SourceDatasets={'DOI': '10.18112/openneuro.ds000113.v1.3.0', 'URL': 'https://openneuro.org/datasets/ds000113/versions/1.3.0', 'Version': '1.3.0'}
    ds003766/dataset_description.json:
      SourceDatasets=[{'URL': 'file://./sourcedata/rawdata'}]
    ds003900/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.1016/j.neuroimage.2015.02.071'}, {'DOI': 'doi:10.1101/2020.06.17.154666'}, {'DOI': 'doi:10.18112/openneuro.ds001796.v1.4.1', 'URL': 'https://openneuro.org/datasets/ds001796/versions/1.4.1', 'Version': '1.4.1'}, {'DOI': 'doi:
    10.18112/openneuro.ds000030.v1.0.0', 'URL': 'https://openneuro.org/datasets/ds000030/versions/1.0.0', 'Version': '1.0.0'}, {'DOI': 'doi:10.18112/openneuro.ds000201.v1.0.3', 'URL': 'https://openneuro.org/datasets/ds000201/versions/1.0.3', 'Version': '1.0.3'},
     {'DOI': 'doi:10.1016/j.nicl.2019.101907'}]
    ds004401/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.18112/openneuro.ds004230.v2.3.1', 'URL': 'https://openneuro.org/datasets/ds004230/versions/2.3.1', 'Version': '2.3.1'}]
    ds004630/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds004630'}]
    ds004917/dataset_description.json:
      SourceDatasets=[{'DOI': '10.18112/openneuro.ds004917.v1.0.0', 'Version': '1.0'}]
    ds005261/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.18112/openneuro.ds005261.v2.0.0', 'URL': 'https://openneuro.org/datasets/ds005261', 'Version': '2.0.0'}]
    ds005364/dataset_description.json:
      SourceDatasets=[{'DOI': '', 'Version': '1.0'}]
    ds005472/dataset_description.json:
      SourceDatasets=[{'URL': 'https://doi.org/doi:10.18112/openneuro.ds004331.v1.0.4', 'DOI': 'doi:10.18112/openneuro.ds004331.v1.0.4'}]
    ds005481/dataset_description.json:
      SourceDatasets=[{'URL': 'https://doi.org/doi:10.18112/openneuro.ds004496.v2.1.2', 'DOI': 'doi:10.18112/openneuro.ds004496.v2.1.2'}]
    ds005571/dataset_description.json:
      SourceDatasets=[{'DOI': '', 'Version': '1.0'}]
    ds005589/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds005589', 'Version': 'October 23 2024'}]
    ds005603/dataset_description.json:
      SourceDatasets=[{'URL': 's3://dicoms/studies/correlates', 'Version': 'April 11 2011'}]
    ds005687/dataset_description.json:
      SourceDatasets=[{'URL': 'bids:sourcedata:'}]
    ds005787/dataset_description.json:
      SourceDatasets=[{'DOI': '...'}]
    ds005810/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.18112/openneuro.ds004496.v1.2.2'}]
    ds005811/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.18112/openneuro.ds004496.v1.2.2'}]
    ds005815/dataset_description.json:
      SourceDatasets=[{'URL': 'N/A', 'Version': 'N/A'}]
    ds005907/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds004595/versions/1.0.0', 'DOI': 'doi:10.18112/openneuro.ds004595.v1.0.0'}]
    ds005920/dataset_description.json:
      SourceDatasets=[{'Description': 'This dataset is original and does not derive from any existing source datasets.'}]
    ds006035/dataset_description.json:
      SourceDatasets=[{'DOI': 'doi:10.18112/openneuro.TBD'}]
    ds006126/dataset_description.json:
      SourceDatasets=[{'Gimme': 'https://example.com/source_dataset'}]
    ds006143/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006131'}]
    ds006182/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006131'}]
    ds006185/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006131'}]
    ds006188/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006131'}]
    ds006189/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006185'}, {'URL': 'https://openneuro.org/datasets/ds006131'}]
    ds006190/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006189'}, {'URL': 'https://openneuro.org/datasets/ds006185'}, {'URL': 'https://openneuro.org/datasets/ds006131'}]

So if a dataset has there DatasetType=derivative and points to a single other openneuro dataset (via URL or DOI -- analyze the formats there to parse out dataset id), it must be a derivative of that other dataset.

E.g.

If it points to more than one dataset, e.g.

    $> tools/find_attrs SourceDatasets DatasetType -- ds006190/dataset_description.json
    ds006190/dataset_description.json:
      SourceDatasets=[{'URL': 'https://openneuro.org/datasets/ds006189'}, {'URL': 'https://openneuro.org/datasets/ds006185'}, {'URL': 'https://openneuro.org/datasets/ds006131'}]
      DatasetType=derivative

we should 

- do have the `study-ds006190/` dataset, 
- link all those multiple raw as submodules under sourcedata/{original_id}, e.g. sourcedata/ds006189 and so on
  - note that there then should be no single "sourcedata/raw"
- link derivative in question (ds006190) under derivatives/{codename} where codename is to be figured out as a short word based on what it is .... TODO

#### derivatives/bids-validator.{json,txt}

After introdcuing modification, or just upon request we need to run
`bids-validator-deno` on each study dataset, and store text and json
outputs under derivatives/.

Result of bids-validator should be used later to populate some bids-valid
column in studies.tsv.

# Some non-specific desires yet

