# 
# @author: Allan
#

from tqdm import tqdm
from typing import List, Dict
import re
from torch.utils.data import Dataset
from torch.utils.data._utils.collate import default_collate
import torch
from transformers import PreTrainedTokenizer
import collections
import numpy as np
from src.data.data_utils import convert_iobes

Instance = collections.namedtuple('Instance', 'words ori_words labels')
Instance.__new__.__defaults__ = (None,) * 3

Feature = collections.namedtuple('Feature', 'input_ids attention_mask token_type_ids orig_to_tok_index label_ids')
Feature.__new__.__defaults__ = (None,) * 6


def convert_instances_to_feature_tensors(instances: List[Instance],
                                         tokenizer: PreTrainedTokenizer,
                                         label2idx: Dict[str, int]) -> List[Feature]:
    features = []
    # max_candidate_length = -1

    for idx, inst in enumerate(instances):
        words = inst.ori_words
        orig_to_tok_index = []
        tokens = []
        for i, word in enumerate(words):
            """
            Note: by default, we use the first wordpiece token to represent the word
            If you want to do something else (e.g., use last wordpiece to represent), modify them here.
            """
            orig_to_tok_index.append(len(tokens))
            ## tokenize the word into word_piece / BPE
            ## NOTE: adding a leading space is important for BART/GPT/Roberta tokenization.
            ## Related GitHub issues:
            ##      https://github.com/huggingface/transformers/issues/1196
            ##      https://github.com/pytorch/fairseq/blob/master/fairseq/models/roberta/hub_interface.py#L38-L56
            ##      https://github.com/ThilinaRajapakse/simpletransformers/issues/458
            word_tokens = tokenizer.tokenize(" " + word)
            for sub_token in word_tokens:
                tokens.append(sub_token)
        labels = inst.labels
        label_ids = [label2idx[label] for label in labels] if labels else None
        input_ids = tokenizer.convert_tokens_to_ids([tokenizer.cls_token] + tokens + [tokenizer.sep_token])
        segment_ids = [0] * len(input_ids)
        input_mask = [1] * len(input_ids)

        features.append(Feature(input_ids=input_ids,
                                attention_mask=input_mask,
                                orig_to_tok_index=orig_to_tok_index,
                                token_type_ids=segment_ids,
                                label_ids=label_ids))
    return features


class NERDataset(Dataset):

    def __init__(self, file: str,
                tokenizer: PreTrainedTokenizer,
                 number: int = -1, digit2zero:bool=True):
        """
        Read the dataset into Instance
        :param digit2zero: convert the digits into 0, which is a common practice for LSTM-CRF.
        """
        self.digit2zero = digit2zero
        insts = self.read_txt(file=file, number=number)
        self.insts_ids = convert_instances_to_feature_tensors(insts, tokenizer)
        self.tokenizer = tokenizer

    def read_txt(self, file: str, number: int = -1) -> List[Instance]:
        print("Reading file: " + file)
        insts = []
        with open(file, 'r', encoding='utf-8') as f:
            words = []
            ori_words = []
            labels = []
            for line in tqdm(f.readlines()):
                line = line.rstrip()
                if line == "":
                    labels = convert_iobes(labels)
                    insts.append(Instance(words=words, ori_words=ori_words, labels=labels))
                    words = []
                    ori_words = []
                    labels = []
                    if len(insts) == number:
                        break
                    continue
                ls = line.split()
                word, label = ls[0],ls[-1]
                ori_words.append(word)
                if self.digit2zero:
                    word = re.sub('\d', '0', word) # replace digit with 0.
                words.append(word)
                labels.append(label)
        print("number of sentences: {}".format(len(insts)))
        return insts

    def __len__(self):
        return len(self.insts_ids)

    def __getitem__(self, index):
        return self.insts_ids[index]

    def collate_fn(self, batch:List[Feature]):
        word_seq_len = [len(feature.orig_to_tok_index) for feature in batch]
        max_seq_len = max(word_seq_len)
        max_wordpiece_length = max([len(feature.input_ids) for feature in batch])
        for i, feature in enumerate(batch):
            padding_length = max_wordpiece_length - len(feature.input_ids)
            input_ids = feature.input_ids + [self.tokenizer.pad_token_id] * padding_length
            mask = feature.attention_mask + [0] * padding_length
            type_ids = feature.token_type_ids + [self.tokenizer.pad_token_type_id] * padding_length
            padding_word_len = max_seq_len - len(feature.orig_to_tok_index)
            orig_to_tok_index = feature.orig_to_tok_index + [0] * padding_word_len

            batch[i] = Feature(input_ids=np.asarray(input_ids),
                               attention_mask=np.asarray(mask), token_type_ids=np.asarray(type_ids),
                               orig_to_tok_index=np.asarray(orig_to_tok_index),
                               label_ids=np.asarray(feature.label_ids))
        results = Feature(*(default_collate(samples) for samples in zip(*batch)))
        return results

# class Reader:
#
#     def __init__(self, digit2zero:bool=True):
#         """
#         Read the dataset into Instance
#         :param digit2zero: convert the digits into 0, which is a common practice for LSTM-CRF.
#         """
#         self.digit2zero = digit2zero
#         self.vocab = set()
#
#     def read_txt(self, file: str, number: int = -1) -> List[Instance]:
#         print("Reading file: " + file)
#         insts = []
#         with open(file, 'r', encoding='utf-8') as f:
#             words = []
#             ori_words = []
#             labels = []
#             for line in tqdm(f.readlines()):
#                 line = line.rstrip()
#                 if line == "":
#                     insts.append(Instance(Sentence(words, ori_words), labels))
#                     words = []
#                     ori_words = []
#                     labels = []
#                     if len(insts) == number:
#                         break
#                     continue
#                 ls = line.split()
#                 word, label = ls[0],ls[-1]
#                 ori_words.append(word)
#                 if self.digit2zero:
#                     word = re.sub('\d', '0', word) # replace digit with 0.
#                 words.append(word)
#                 self.vocab.add(word)
#                 labels.append(label)
#         print("number of sentences: {}".format(len(insts)))
#         return insts
#


