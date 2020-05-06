#!/usr/bin/python3.6
#coding:utf-8

"""
@software: PyCharm
@file: dupicate_conetnt.py
"""
import re
from simhash import Simhash, SimhashIndex
from limpid_tools.tool import *
import sys
import jieba
import jieba.analyse
import numpy as np
import json


# Redis configuration
REDIS_URI = '127.0.0.1'
REDIS_PORT = 6379
REDIS_PASSWORD = ''
REDIS_DB = 4
REDIS_KEY = 'biwen'
REDIS_SIMILAR_KEY = 'sim_biwen'

# MongoDB configuration
MONGO_URI = 'localhost'
MONGO_PORT = 27017
MONGO_DB = 'biwen'
MONGO_COLLECTION = 'biwen'
MONGO_USER = ''
MONGO_PASSWORD = ''
MONGO_BATCH_SIZE = 50

redis_client = get_redis_client(host=REDIS_URI, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD)
mongo_client = get_mongo_client(host=MONGO_URI, port=MONGO_PORT, username=MONGO_USER, password=MONGO_PASSWORD)


def string_hash(source):
    if source == "":
        return 0
    else:
        x = ord(source[0]) << 7
        m = 1000003
        mask = 2 ** 128 - 1
        for c in source:
            x = ((x * m) ^ ord(c)) & mask
        x ^= len(source)
        if x == -1:
            x = -2
        x = bin(x).replace('0b', '').zfill(64)[-64:]
        # print(source,x)
        return str(x)

        '''
        以下是使用系统自带hash生成，虽然每次相同的会生成的一样，
        不过，对于不同的汉子产生的二进制，在计算海明码的距离会不一样，
        即每次产生的海明距离不一致
        所以不建议使用。
        '''
    # x=str(bin(hash(source)).replace('0b','').replace('-','').zfill(64)[-64:])
    # print(source,x,len(x))
    # return x

def simhash(content):
    seg = jieba.cut(content)
    # jieba.analyse.set_stop_words('stopword.txt')
    keyWord = jieba.analyse.extract_tags('|'.join(seg), topK=20, withWeight=True, allowPOS=())#在这里对jieba的tfidf.py进行了修改
    #将tags = sorted(freq.items(), key=itemgetter(1), reverse=True)修改成tags = sorted(freq.items(), key=itemgetter(1,0), reverse=True)
    #即先按照权重排序，再按照词排序
    keyList = []
    # print(keyWord)
    for feature, weight in keyWord:
        weight = int(weight * 20)
        feature = string_hash(feature)
        temp = []
        for i in feature:
            if(i == '1'):
                temp.append(weight)
            else:
                temp.append(-weight)
        # print(temp)
        keyList.append(temp)
    list1 = np.sum(np.array(keyList), axis=0)
    # print(list1)
    if(keyList==[]): #编码读不出来
        return '00'
    simhash = ''
    for i in list1:
        if(i > 0):
            simhash = simhash + '1'
        else:
            simhash = simhash + '0'
    return simhash

def hammingDis(sim_hash,com_simhash):
    t1 = '0b' + sim_hash
    t2 = '0b' + com_simhash
    n=int(t1, 2) ^ int(t2, 2)
    i=0
    while n:
        n &= (n-1)
        i+=1
    return i

def is_exist_similar(content=None,redis_similar_key=REDIS_SIMILAR_KEY,add_redis_value=False):
    # 判断content是否与redis_key保存的hash值相似,判断距离为3，距离值越小说明越相似
    get_redis = get_redis_client(host=REDIS_URI, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD)
    redis_value_set = get_redis.smembers(redis_similar_key)
    is_similar = False
    if content:
        simhash_finger = simhash(content)
        for re_key in redis_value_set:
            if re_key:
                dist = hammingDis(str(re_key).replace('b', '').replace('\'', ''), simhash_finger)
                if dist < 3:  # 汉明距离小于3的判断为文本相似
                    is_similar = True
    if add_redis_value:
        if not is_similar:
            get_redis_client.sadd(REDIS_SIMILAR_KEY, bytes(simhash_finger, encoding='utf-8'))
            print('add finger:', content)
    return is_similar

def map_content_hash_mongo_redis(mongo_client=None,redis_client=None,):
    # 同步mongo中已有的文本进行hash值存储
    redis_client = get_redis_client(host=REDIS_URI, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD)
    redis_value_set = redis_client.smembers(REDIS_SIMILAR_KEY)
    mongo_client = get_mongo_client(host=MONGO_URI, port=MONGO_PORT, username=MONGO_USER, password=MONGO_PASSWORD)
    mongo_data = get_mongo_data(client=mongo_client, db=MONGO_DB, col=MONGO_COLLECTION, my_query=None, no_timeout=False, my_sort=None)
    is_similar = False
    # 建立mongo原有的simhash
    for con_idx,con in enumerate(mongo_data):
        simhash_finger = simhash(con['content'])
        # 计算相似度
        for re_key in redis_value_set:
            if re_key:
                dist = hammingDis(str(re_key).replace('b','').replace('\'',''),simhash_finger)
                if dist<3:  # 汉明距离小于3的判断为文本相似
                    is_similar = True
        if not is_similar:
            redis_client.sadd(REDIS_SIMILAR_KEY,bytes(simhash_finger,encoding='utf-8'))
            print('add finger:',con_idx,con['url'])





