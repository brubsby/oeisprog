import os
import collections

root_dir = os.path.expanduser("~/Repos/oeisprog/progs/")
languages = collections.Counter()
language_seqs = collections.defaultdict(list)

for root, dirs, files in os.walk(root_dir):
    for file in files:
        if not file.startswith("A"):
            continue
        parts = file.split("_")
        if len(parts) >= 3:
            # Axxxxxx_lang_index.ext
            a_num = parts[0]
            # lang is everything between Axxxxxx and the index.
            lang = "_".join(parts[1:-1])
            languages[lang] += 1
            language_seqs[lang].append(a_num)

print(f"{'Language':<40} | {'Count':<10} | {'Sequences (if < 10)'}")
print("-" * 100)
for lang, count in languages.most_common():
    seq_list = ""
    if count < 10:
        seq_list = " ".join(sorted(list(set(language_seqs[lang]))))
    print(f"{lang:<40} | {count:<10} | {seq_list}")
