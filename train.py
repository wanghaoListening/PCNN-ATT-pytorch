# -*- coding: utf-8 -*-

import os
import math
import gensim
import time
import sys
import json
import copy
import operator
import argparse
import utils

import numpy as np
from scipy.misc import logsumexp
from random import shuffle

from scipy.sparse import hstack, vstack
from collections import defaultdict, Counter
from gensim.models import word2vec
from sklearn import metrics

from utils import loader, helper
from model.PCNN_ATT import PCNN_ATT


import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.autograd as autograd



def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', type=str, default='data/')
    # parser.add_argument('--train_file', type=str, default='data/train.txt')
    # parser.add_argument('--test_file', type=str, default='data/test.txt')
    # parser.add_argument('--vocab_file', type=str, default='data/vec.bin')
    # parser.add_argument('--rel_file', type=str, default='data/relation2id.txt')
    parser.add_argument('--save_dir', type=str, default='saved_models')

    # Model parameters
    parser.add_argument('--emb_dim', type=int, default=50, help='Word embedding dimension.')
    parser.add_argument('--pos_dim', type=int, default=5, help='Position embedding dimension.')
    parser.add_argument('--pos_limit', type=int, default=30, help='Position embedding length limit.')
    parser.add_argument('--num_conv', type=int, default=230, help='The number of convolutional filters.')
    parser.add_argument('--win_size', type=int, default=3, help='Convolutional filter size.')
    parser.add_argument('--dropout', type=float, default=0.5, help='The rate at which randomly set a parameter to 0.')
    parser.add_argument('--lr', type=float, default=0.001, help='Applies to SGD.')
    parser.add_argument('--num_epoch', type=int, default=15)

    parser.add_argument('--num_trial', type=int, default=50000)
    parser.add_argument('--trial', type=bool, default=False)

    parser.add_argument('--cuda', type=bool, default=torch.cuda.is_available())
    parser.add_argument('--cpu', action='store_true', help='Ignore CUDA.')
    args = parser.parse_args()

    if args.cpu:
        args.cuda = False
        
    # make opt
    opt = vars(args)

    opt['train_file'] = opt['data_dir'] + '/' + 'train.txt'
    opt['test_file'] = opt['data_dir'] + '/' + 'test.txt'
    opt['vocab_file'] = opt['data_dir'] + '/' + 'vec.bin'
    opt['rel_file'] = opt['data_dir'] + '/' + 'relation2id.txt'


    # Pretrained word embedding
    print "Load pretrained word embedding"
    w2v_model = gensim.models.KeyedVectors.load_word2vec_format(opt['vocab_file'], binary=True)
    word_list = [u'UNK'] + w2v_model.index2word
    word_vec = w2v_model.syn0

    word_map = {}

    for id, word in enumerate(word_list):
        word_map[word] = id

    assert opt['emb_dim'] == w2v_model.syn0.shape[1]


    # Read from relation2id.txt to build a dictionary: rel_map
    rel_map = {}
            
    with open(opt['rel_file'],'rb') as f:
        for item in f:
            [relation, id] = item.strip('\n').split(' ')
            rel_map[relation] = int(id)

    opt['num_rel'] = len(rel_map)
    opt['vocab_size'] = len(word_list)


    # Load data
    all_data = loader.DataLoader(opt['train_file'], opt['test_file'], opt, word_map, rel_map)
    opt['pos_e1_size'] = all_data.pos_max_e1 - all_data.pos_min_e1 + 1
    opt['pos_e2_size'] = all_data.pos_max_e2 - all_data.pos_min_e2 + 1
    opt['pos_min_e1'] = all_data.pos_min_e1
    opt['pos_min_e2'] = all_data.pos_min_e2

    assert opt['pos_e1_size'] == opt['pos_e2_size']

    helper.check_dir(opt['save_dir'])
    helper.print_config(opt)


    PCNN_ATT_model = PCNN_ATT(word_vec, opt)
    PCNN_ATT_model.cuda()

    loss_function = nn.NLLLoss()
    optimizer = optim.SGD(PCNN_ATT_model.parameters(), lr=opt['lr'])

    start_time = time.time()
    
    print "Training starts."

    for epoch in xrange(opt['num_epoch']):
        
        print 'The running time of epoch %d:' % (epoch),
        
        total_loss = torch.Tensor([0]).cuda()
        
        if opt['trial']:
            train_part = all_data.bags_train.keys()[:opt['num_trial']]
        else:
            train_part = all_data.bags_train.keys()[:]
                
        shuffle(train_part) 
        
        for index, bag_name in enumerate(train_part):
            
            # if index % 10000 == 0:
            #     print 'index == ', index
                
            optimizer.zero_grad()
                
            sentence_list = all_data.bags_train[bag_name]
            
            target = int(all_data.train_rel[sentence_list[0]])

            try:
                log_probs = PCNN_ATT_model(sentence_list, target, all_data)
            except:
                print index, len(sentence_list)
                raise
                
            target = autograd.Variable(torch.LongTensor([target]).cuda())
                
            loss = loss_function(log_probs, target)
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.data
            
        # Eval and get the AUC
        recall, precision = PCNN_ATT_model.test(all_data)
        test_AUC = metrics.auc(recall, precision)
        
        # Save parameters in each epoch
        model_file = opt['save_dir'] + '/checkpoint_epoch_%s.tar' % epoch

        torch.save({
           'state_dict': PCNN_ATT_model.state_dict(),
        }, model_file )
        
        best_file = opt['save_dir'] + '/best_model.tar'
        
        if epoch == 0 or best_AUC < test_AUC:
            
            best_AUC = test_AUC
            
            torch.save({
               'state_dict': PCNN_ATT_model.state_dict(),
            }, best_file )
        
            
        stop_time = time.time()   
        print '%f; the total loss: %f; the AUC of P/R curve: %f' % (stop_time - start_time, total_loss.cpu().numpy()[0], test_AUC)
        start_time = stop_time


if __name__ == "__main__":
    main()





    


