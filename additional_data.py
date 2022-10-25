import json
import re
from io import StringIO
from operator import itemgetter

import pandas as pd
import requests
from Bio import SeqIO

with open('databases/thermomutdb.json') as json_file:
    thermomut_db = json.load(json_file)

# filter database

# important columns
column_keep = ["dtm", "swissprot", "uniprot", "mutation_code"]
thermomut_db = [x for x in thermomut_db if all(
    v is not None for v in itemgetter(*column_keep)(x))]

# filter invalid uniport ids
thermomut_db = [x for x in thermomut_db if re.match(
    r"(.*)([A-Z0-9]{6})(.*)", x["swissprot"])]

# filter by pH
thermomut_db = [x for x in thermomut_db if x["ph"]]
thermomut_db = [x for x in thermomut_db if 5 < x["ph"] < 9]

# filter by length
thermomut_db = [x for x in thermomut_db if x["length"]]
thermomut_db = [x for x in thermomut_db if 80 < x["length"] < 10000]

# convert to dataframe
thermomut_df = pd.DataFrame(
    [itemgetter(*column_keep)(x) for x in thermomut_db], columns=column_keep)

# find swissprot ids into string
thermomut_df['swissprot'].replace(
    to_replace=r"(.*)([A-Z0-9]{6})(.*)", value=r"\2", regex=True, inplace=True)

# make groups
# get number of groups
thermomut_df.groupby("swissprot").ngroups
# make them and filter thoses with 4 or more proteins
thermomut_df = thermomut_df.groupby(
    "swissprot").filter(lambda x: len(x) >= 4)
# make a new column with the group id, starting at 1
thermomut_df['gid'] = thermomut_df.groupby("swissprot").ngroup().add(1)

# fetch sequences from uniprot
thermomut_df["protein_sequence"] = ""
thermomut_df["acc_id"] = ""

base_url = "https://www.uniprot.org/uniprot/"

for index, row in thermomut_df.iterrows():
    sequence = ""

    # try to fetch sequence from swissprot id
    try:
        swissprot_id = thermomut_df.loc[index, "swissprot"]
        url = base_url + swissprot_id + ".fasta"
        response = requests.post(url)
        sequence = str(SeqIO.read(
            StringIO(''.join(response.text)), 'fasta').seq)
        thermomut_df.loc[index, "acc_id"] = swissprot_id
    except:
        # otherwise try uniprot id
        try:
            uniprot_id = thermomut_df.loc[index, "uniprot"]
            url = base_url + uniprot_id + ".fasta"
            response = requests.post(url)
            sequence = str(SeqIO.read(
                StringIO(''.join(response.text)), 'fasta').seq)
            thermomut_df.loc[index, "acc_id"] = uniprot_id
        except:
            # both fetch failed, sequence is empty
            sequence = "accession id not found"

    if sequence:
        # apply mutation(s) on sequence
        mutation_code = thermomut_df.loc[index, "mutation_code"]
        match = re.findall(r"([a-z]+)([0-9]+)([a-z]+)", mutation_code, re.I)
        for mutation in match:
            pos = int(mutation[1])
            try:
                # try to apply the mutation to the sequence
                if sequence[pos-1] == mutation[0]:
                    sequence = sequence[:(pos-1)] + \
                        mutation[2] + sequence[pos:]
            except:
                # if it fails then the sequence might be invalid
                sequence = "can't apply mutation"
                break
    thermomut_df.loc[index, "protein_sequence"] = sequence

# filter empty sequences
thermomut_df = thermomut_df[thermomut_df["protein_sequence"].str.len() != 0]

thermomut_df["type"] = "mutated"

for gid, acc_id in zip(thermomut_df["gid"].unique(), thermomut_df["acc_id"].unique()):
    url = base_url + acc_id + ".fasta"
    response = requests.post(url)
    sequence = str(SeqIO.read(
        StringIO(''.join(response.text)), 'fasta').seq)
    thermomut_df = thermomut_df.append({"gid": gid,
                                        "protein_sequence": sequence,
                                        "dtm": 0,
                                        "acc_id": acc_id,
                                        "type": "wildtype"},
                                       ignore_index=True)

# filter group with less than 4 proteins
thermomut_df = thermomut_df.groupby(
    "gid").filter(lambda x: len(x) >= 4)

thermomut_df.sort_values(by=["gid", "type"], inplace=True)

# final dataframe
thermomut_df = thermomut_df[[
    "gid", "protein_sequence", "dtm", "acc_id", "type"]].reset_index(drop=True)

thermomut_df.to_csv("databases/thermomut_grouped.csv")