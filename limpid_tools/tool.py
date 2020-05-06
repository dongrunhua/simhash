# -*- coding: utf-8 -*-
import os
import re
import time
import json
import redis
import random
import scrapy
import pymongo
import datetime
from html import unescape
from pprint import pprint
from urllib.parse import urlparse
from gne import GeneralNewsExtractor
from PyPDF2 import PdfFileReader
from scrapy.http.cookies import CookieJar
from scrapy.utils.request import request_fingerprint

from limpid_tools.custom_constant import *

extractor = GeneralNewsExtractor()


# 去重模块
# 建立redis连接
def get_redis_client(host=None, port=None, db=None, password=None):
    redis_client = redis.Redis(host=host, port=port, db=db, password=password)
    return redis_client


# 通过redis set去重
def is_not_exist(my_key=None, my_value=None, redis_client=None, add_key=False):
    my_value = url_auto_to_request_finger(my_value)
    exist = sismember_key(my_key=my_key, my_value=my_value, redis_client=redis_client)
    if not exist:
        if add_key:
            sadd_key(my_key=my_key, my_value=my_value, redis_client=redis_client)
        return True
    else:
        return False


# 判断 my_value 元素是否是集合 my_key 的成员
def sismember_key(my_key=None, my_value=None, redis_client=None):
    if redis_client.sismember(my_key, my_value):
        return True
    else:
        return False


# 向 my_key 集合添加一个 my_value 成员
def sadd_key(my_key=None, my_value=None, redis_client=None):
    redis_client.sadd(my_key, my_value)


# 移除 my_key 集合中的 my_value 成员
def srem_key(my_key=None, my_value=None, redis_client=None):
    redis_client.srem(my_key, my_value)


# 通过redis string去重
def is_not_repeated(my_key=None, option=0, redis_client=None):
    if is_repeated(my_key=my_key, option=option, redis_client=redis_client):
        return False
    else:
        return True


# 通过redis string去重
def is_repeated(my_key=None, option=0, redis_client=None):
    my_key = url_auto_to_request_finger(my_key)
    repeated = get_key(my_key, redis_client=redis_client)
    if repeated:
        return True
    else:
        if option == 1:
            set_key(my_key, redis_client=redis_client)
        return False


# 获取 my_key 的值
def get_key(my_key=None, redis_client=None):
    if redis_client.get(my_key):
        return True
    else:
        return False


# 设置指定 my_key 的值为 1
def set_key(my_key, redis_client=None):
    redis_client.set(my_key, 1)


# 删除 my_key 的值
def del_key(my_key, redis_client=None):
    redis_client.delete(my_key)


# url 自动转为 scrapy request 指纹
def url_auto_to_request_finger(my_key=None):
    if my_key is not None and is_url(my_key):
        url = str(my_key).replace('https://', 'http://')
        request = scrapy.Request(url)
        request_finger = get_scrapy_request_finger(request)
        return request_finger
    return my_key


# 判断是否是 url
def is_url(my_key=None):
    # http, mailto
    if my_key is not None and (my_key.startswith('http://') or my_key.startswith('https://') or my_key.startswith('mailto:')):
        return True
    return False


# 取到 scrapy_request 的指纹
def get_scrapy_request_finger(request=None):
    if request is not None:
        return request_fingerprint(request)
    return request


# 根据xpath列表拿到结果
def get_xpath_result(response=None, xpath_list=None, min_length=1):
    for xpath in xpath_list:
        text = response.xpath(xpath)
        if is_text(text, min_length):
            return text
    return []


# 判断是否为文本
def is_text(text=None, min_length=1):
    if text and len(str(text).strip()) >= min_length:
        return True
    else:
        return False


# 匹配某个网站完全ok，同一网站下不同子域名，则同一xpath语法，可能后续存在问题
def match_info_by_domain(domain_list=None, info_list=None):
    # 存在则提取
    # for info in info_list:
    #     domain = info['domain']
    #     if domain in domain_list:
    #         return info
    # return []

    # -1开始判断，遍历完-1，才遍历-2
    for domain in reversed(domain_list):
        for info in info_list:
            if domain == info['domain']:
                return info
    return None


def remove_common_top_level_domains(domain=None, common_top_level_domains=None):
    domain = domain + '.'
    for common_top_level_domain in common_top_level_domains:
        domain = domain.replace(common_top_level_domain + '.', '.')
    domain = domain[:-1]
    return domain


def get_xpath_value_result(response=None, xpath_list=None, min_length=1, just_p=False, get_str=True):
    for xpath in xpath_list:
        if xpath.endswith(']'):
            if just_p:
                _xpath = ''.join(xpath + '//p')
            else:
                _xpath = xpath
            text = get_xpath_value(response=response, xpath=_xpath, min_length=min_length, get_str=get_str)
            if text:
                return text
        text = get_xpath_value(response=response, xpath=xpath, min_length=min_length, get_str=get_str)
        if text:
            return text
    return None


def get_xpath_value(response=None, xpath=None, min_length=1, get_str=True):
    text_1 = response.xpath(xpath).get()
    text_2 = response.xpath(xpath).extract()
    if get_str:
        text_2 = ''.join(text_2)
    text = text_1 if len(str(text_1)) > len(str(text_2)) else text_2
    if is_text(text, min_length):
        return text
    else:
        return None


# 新闻content过滤标签等（直接套用/直接重写）
def filter_long(text=None, base_img=None, img_special=False, extra_res=None, save_img=True, save_a=False,
                set_min_word=False, min_length=1, replace_word='', a_href_tag_tuple=None, a_text_tag_tuple=None):
    if text:
        # 注：所有HTML标签都被替换为''
        # replace_word = REPLACE_WORD

        # 去掉style、script等标签和其中的内容
        filter_res = [
            r'<!--.*?-->',
            r'<\s*?style.*?>.*?<\s*?\/\s*?style.*?>',
            r'<\s*?script.*?>.*?<\s*?\/\s*?script.*?>',
        ]
        # 去掉额外的一些内容
        if extra_res:
            filter_res = extra_res + filter_res
        for filter_re in filter_res:
            data = re.findall(filter_re, text, re.DOTALL)
            for dat in data:
                text = text.replace(dat, replace_word)

        # 替换为'\n'的标签单独写正则（具有换行意义的HTML标签）
        my_re_list = [
            # 精准
            r'<\s*?/?p.*?>',
            r'<\s*?/?li.*?>',
            r'<\s*?/?tr.*?>',
            r'<br>',
            # 较少
            r'<\s*?/?div.*?>',
        ]
        for my_re in my_re_list:
            data = re.findall(my_re, text, re.DOTALL)
            for dat in data:
                text = text.replace(dat, '\n')

        # 保存指定HTML标签的指定属性
        if save_img or save_a:
            save_tag_info_list = []
            base_re_head = r'<\s*?{save_tag}\s+?.*?(?:{save_attr})="'
            base_re_tail = r'".*?>'
            if save_img:
                save_tag_info_list.append(
                    (base_re_head.format(save_tag='img', save_attr='src|data-original'), base_re_tail)
                )
            if save_a:
                save_tag_info_list.append(
                    (base_re_head.format(save_tag='a', save_attr='href'), base_re_tail)
                )
            for save_tag_info in save_tag_info_list:
                # 去掉save_tag标签中src/href以外的内容（保留图片链接/超链接）
                re_head = save_tag_info[0]
                re_tail = save_tag_info[1]
                goal_hrefs = re.findall(r'(' + re_head + r'(.*?)' + re_tail + r')', text)
                if goal_hrefs:
                    # 重命名（确保之前调用此方法，传参不报错）
                    base_href = base_img
                    for goal_href in goal_hrefs:
                        if base_href:
                            goal_link = href_auto_to_url(base_href, goal_href[1])
                        else:
                            goal_link = goal_href[1]
                        if goal_link and is_url(goal_link):
                            if save_img and 'img' in re_head:
                                # 图片链接后添空行
                                goal_link = goal_link + '\n'
                            else:
                                if save_a:
                                    # a标签@href属性添加开始和结束标记
                                    if a_href_tag_tuple:
                                        href_tag_start = a_href_tag_tuple[0]
                                        href_tag_end = a_href_tag_tuple[1]
                                        goal_link = href_tag_start + goal_link + href_tag_end
                                    # a标签text()属性添加开始标记
                                    if a_text_tag_tuple:
                                        a_tag_start = a_text_tag_tuple[0]
                                        goal_link = goal_link + a_tag_start
                                    # 只声明保留超链接，无相关标记的：超链接后添空行
                                    if (not a_href_tag_tuple) and (not a_text_tag_tuple):
                                        goal_link = goal_link + '\n'
                            text = text.replace(goal_href[0], goal_link)

        # 所有a标签text()属性添加结束标记
        if save_a and a_text_tag_tuple:
            data = re.findall(r'</a.*?>', text, re.DOTALL)
            for dat in data:
                a_tag_end = a_text_tag_tuple[1]
                text = text.replace(dat, a_tag_end)

        # 去掉所有的HTML标签
        data = re.findall(r'<.*?>', text, re.DOTALL)
        for dat in data:
            text = text.replace(dat, replace_word)

        if set_min_word and not is_text(text=text, min_length=min_length):
            return None

        # 去掉连续'\s'
        text = replace_n_n_to_1(text=text, replace_word='\r\n')
        text = text.strip()

    return text


# 删去列表重复元素
def delete_repeated_text_list_element(text_list=None):
    new_text_list = list(set(text_list))
    new_text_list.sort(key=text_list.index)
    return new_text_list


# 删去文本重复元素
def delete_repeated_text_element(text=None, split_word=None):
    if text:
        old_text_list = text.split(split_word)
        new_text_list = delete_repeated_text_list_element(text_list=old_text_list)
        text = split_word.join(new_text_list)
    return text


# 自动转换href到url
def href_auto_to_url(base_url=None, href=None):
    if href:
        if base_url:
            if is_url(href):
                final_url = href
            else:
                u1 = urlparse(base_url)
                scheme1, netloc1, path1, params1, query1, fragment1 = u1[0], u1[1], u1[2], u1[3], u1[4], u1[5]
                if href.startswith('://'):
                    final_url = scheme1 + href
                else:
                    u2 = urlparse(href)
                    scheme2, netloc2, path2, params2, query2, fragment2 = u2[0], u2[1], u2[2], u2[3], u2[4], u2[5]
                    scheme = get_para(scheme1, scheme2)
                    netloc = get_para(netloc1, netloc2)
                    path = get_para(path1, path2)
                    # params = get_para(params1, params2)
                    query = get_para(query1, query2)
                    fragment = get_para(fragment1, fragment2)
                    if is_text(scheme) and is_text(path):
                        final_url = scheme + '://'
                        if path.startswith(netloc1):
                            final_url = final_url + path
                        else:
                            final_url = final_url + netloc + '/' + path
                    else:
                        return None
                    if is_text(query):
                        final_url = final_url + '?' + query
                    if is_text(fragment):
                        final_url = final_url + '#' + fragment
                final_url = final_url.replace('//', '/').replace(':/', '://')
            return final_url
        return href
    return None


def get_para(raw_para, goal_para):
    # final_para = goal_para if goal_para and goal_para != '' else raw_para
    if is_text(goal_para):
        final_para = goal_para
    else:
        final_para = raw_para
    return final_para


# 把连续'某词'替换为单个'某词'
def replace_many_n_to_n(text=None, replace_word=None):
    if text:
        text = re.sub(r'(?:%s)+' % (replace_word, ), replace_word, text)
    return text


# 把连续'\n'替换为单个'\r\n'
def replace_n_n_to_1(text=None, replace_word='\r\n'):
    if text:
        text = re.sub(r'[\n ]*\n[\n ]*', replace_word, text)
        text = text.replace('\r' + replace_word, replace_word)
    return text


# 通用文本过滤
def universal_filter(text):
    if text:
        text = str(text)
        text = unescape(text)
        # text = text.replace('.', '[点]')
        # \u1234
        text = text.replace(u'\u200b', '').replace(r'\u200b', '')
        text = text.replace(u'\u2002', '').replace(r'\u2002', '')
        text = text.replace(u'\u2003', '').replace(r'\u2003', '')
        text = text.replace(u'\u3000', '').replace(r'\u3000', '')
        text = text.replace(u'\ufeff', '').replace(r'\ufeff', '')
        # \x??
        text = text.replace(u'\xa0', ' ').replace(r'\xa0', ' ')
        text = text.replace(u'\x7f', '').replace(r'\x7f', '')
        # &??
        text = text.replace('&nbsp', ' ')
        text = text.replace('&ldquo;', '"')
        text = text.replace('&rdquo;', '"')
        text = text.replace('&bull;', '•')
        text = text.replace('&mdash;', '—')
        text = text.replace('&lsquo;', "'")
        text = text.replace('&rsquo;', "'")
        text = text.replace('&hellip;', '…')
        text = text.replace('&middot;', '·')
        text = text.replace('&quot;', '"')
        text = text.replace('&amp;', '&')
        text = text.replace('&#39;', "'")
        text = text.replace('&deg;', "°")
        text = text.replace('&times;', "×")
        text = text.replace('&beta;', "β")
        text = text.replace('&ndash;', "–")
        # \n, \r, \t
        # text = text.replace('\n', '')
        text = text.replace('\r', '')
        text = text.replace('\t', '')
        text = text.strip()
    return text


# 格式化时间为'yyyy-mm-dd hh:mm:ss'
def formatting_time(my_time):
    if my_time:
        #  转换"xx前"时间
        my_time = convert_n_long_ago_datetime(my_time)

        # 保留数字, '-', ':'
        re_time = r'[^\d\-\:\：]'
        # 匹配数字间的空格, '-', ':', '：'
        re_inter_betw_ymdhms = r'[\-\:\：\s]+'
        # re_inter_betw_hms = r'[\:\：\s]+'
        # 匹配头尾的空格, '-', ':', '：'
        re_head_and_tail_symbol = '[\-\:\：\s]*'
        # 匹配年月日
        re_year = r'^' + re_head_and_tail_symbol + r'(\d{4}' + re_inter_betw_ymdhms + ')'
        re_month = re_head_and_tail_symbol + r'(1[012]' + re_inter_betw_ymdhms + r'|0?[1-9]' + re_inter_betw_ymdhms + ')'
        re_day = r'3[01]|[12]\d|0?[1-9]'
        re_day = r'(' + re_day + r'\s|' + re_day + '$)'
        # 匹配时分秒
        re_hour = r'(2[0-3]' + re_inter_betw_ymdhms + r'|[01]?\d' + re_inter_betw_ymdhms + ')'
        re_minute = r'[0-5]?\d'
        re_minute = r'(' + re_minute + re_head_and_tail_symbol + r'$|' + re_minute + re_inter_betw_ymdhms + ')'
        re_second = r'([0-5]?\d)' + re_head_and_tail_symbol + r'$'

        my_time = re.sub(re_time, ' ', my_time).strip()
        my_time = ' '.join(my_time.split())
        y_m_d_h_m_s = re.findall(re_year + re_month + re_day + re_hour + re_minute + re_second, my_time)
        if y_m_d_h_m_s:
            year, month, day, hour, minute, second = y_m_d_h_m_s[0]
        else:
            re_month = r'^' + re_month
            re_second = r'^' + re_second

            second = ''

            _year = re.findall(re_year, my_time)
            year = _year[0] if _year else str(datetime.datetime.now().year)
            my_time = re.sub(re_year, '', my_time).strip()

            m_d_h_m = re.findall(re_month + re_day + re_hour + re_minute, my_time)
            if m_d_h_m:
                month, day, hour, minute = m_d_h_m[0]
                my_time = re.sub(re_month + re_day + re_hour + re_minute, '', my_time).strip()
            else:
                re_day = r'^' + re_day
                re_hour = r'^' + re_hour
                re_minute = r'^' + re_minute

                _month = re.findall(re_month, my_time)
                month = "".join(_month[0]) if _month else '01'
                my_time = re.sub(re_month, '', my_time).strip()

                _day = re.findall(re_day, my_time)
                day = "".join(_day[0]) if _day else '01'
                my_time = re.sub(re_day, '', my_time).strip()

                _hour = re.findall(re_hour, my_time)
                hour = "".join(_hour[0]) if _hour else '00'
                my_time = re.sub(re_hour, '', my_time).strip()

                _minute = re.findall(re_minute, my_time)
                minute = "".join(_minute[0]) if _minute else '00'
                my_time = re.sub(re_minute, '', my_time).strip()

            if not second:
                _second = re.findall(re_second, my_time)
                second = "".join(_second[0]) if _second else '00'

        year = auto_add_0(year)
        month = auto_add_0(month)
        day = auto_add_0(day)
        hour = auto_add_0(hour)
        minute = auto_add_0(minute)
        second = auto_add_0(second)

        my_time = year + '-' + month + '-' + day + ' ' + hour + ':' + minute + ':' + second

        my_datetime = datetime.datetime.strptime(my_time, "%Y-%m-%d %H:%M:%S")
        if (my_datetime - datetime.datetime.now()) > datetime.timedelta(seconds=0):
            year = int(year) - 1
            my_time = str(year) + '-' + month + '-' + day + ' ' + hour + ':' + minute + ':' + second

    return my_time


# 年月日时分秒 个位自动补0
def auto_add_0(text=None):
    if text:
        if text == '':
            text = 0
        else:
            text = re.sub(r'\D', '', text)
            text = int(text)
        if text < 10:
            text = '0' + str(text)
        else:
            text = str(text)
    return text


def how_long_ago_converted_to_specific_time(text=None):
    specific_time = None

    curr_time = datetime.datetime.now()
    num = int(re.sub(r'\D', '', text))
    if text.endswith('秒前'):
        specific_time = curr_time - datetime.timedelta(seconds=num * pow(60, 0))
    if text.endswith('分钟前'):
        specific_time = curr_time - datetime.timedelta(seconds=num * pow(60, 1))
    if text.endswith('小时前'):
        specific_time = curr_time - datetime.timedelta(seconds=num * pow(60, 2))

    if specific_time:
        specific_time = str(specific_time)[:19]
        return specific_time
    else:
        return text


def str_time_to_datetime(str_time=None):
    result = datetime.datetime.strptime(str_time, "%Y-%m-%d %H:%M:%S")
    return result


# 指定时间内：如48小时内（2 * 24 * 60 * 60）
def within_the_specified_time(release_time=None, last_seconds=0):
    current_time = datetime.datetime.now()
    release_time = str_time_to_datetime(str_time=release_time)
    if (current_time - release_time) <= datetime.timedelta(seconds=last_seconds):
        return True
    else:
        return False


# 指定时间前：如30天前（30 * 24 * 60 * 60）
def before_the_specified_time(release_time=None, seconds_ago=0):
    current_time = datetime.datetime.now()
    release_time = str_time_to_datetime(str_time=release_time)
    if (current_time - release_time) >= datetime.timedelta(seconds=seconds_ago):
        return True
    else:
        return False


# 取到所有文本
# (可以遍历所有xpath取到的text，保存长度最长的text，适用于content，不适用于title和time)
def get_text(response=None, meta_key=None, xpath_list=None, min_length=1, filter_html=True):
    if meta_key in response.meta:
        try:
            text = response.meta[meta_key]
        except:
            text = None
        if filter_html:
            text = filter_long(text)
        if is_text(text, min_length):
            return text
    elif xpath_list:
        for xpath in xpath_list:
            text_1 = response.xpath(xpath).get()
            text_2 = ''.join(response.xpath(xpath).extract())
            text = text_1 if len(str(text_1)) > len(str(text_2)) else text_2
            # 过滤img以外的HTML的标签
            if filter_html:
                text = filter_long(text)
            if is_text(text, min_length):
                return text
    return None


def get_link_field(response, meta_link=None, meta_field=None):
    _link = get_text(response, meta_key=meta_link)
    if _link:
        link = _link
    else:
        link = response.url

    _field = get_text(response, meta_key=meta_field)
    if _field:
        field = _field
    else:
        field = '金融'

    return link, field


def temp_fuc(text=None, my_re=None, my_default=None):
    if text:
        text = re.findall(my_re, text, re.DOTALL)
        text = text[0].replace('：', '') if text else my_default
        return text
    return my_default


def del_text(text=None, my_re_list=None, replace_word=''):
    if text:
        for my_re in my_re_list:
            data = re.findall(my_re, text, re.DOTALL)
            for dat in data:
                text = text.replace(dat, replace_word)
    return text


# 获取今天日期，如'2019-05-11'
def get_date():
    my_date = datetime.date.today()
    return str(my_date)


def get_random_int(min_no, max_no):
    return random.randint(min_no, max_no)


def get_0_to_1_float(min_no, max_no):
    num = get_random_int(min_no, max_no)
    num = num / pow(10, len(str(num)))
    return num


def get_all_filenames(file_dir=None):
    all_filenames = []
    for root, dirs, filenames in os.walk(file_dir):
        # # 当前目录路径
        # print(root)
        # # 当前路径下所有子目录
        # print(dirs)
        # # 当前路径下所有非目录子文件
        # print(filenames)
        all_filenames.append(filenames)
    return all_filenames


def file_is_not_in_file_dir(file_name=None, file_dir=None):
    if not file_is_in_file_dir(file_name=file_name, file_dir=file_dir):
        return True
    else:
        return False


def file_is_in_file_dir(file_name=None, file_dir=None):
    all_filenames = get_all_filenames(file_dir=file_dir)
    for filenames in all_filenames:
        if file_name in filenames:
            return True
    return False


# 拿到m天开始往前n天的日期
def get_m_days_ago_n_days(m=None, n=None):
    date_list = []
    today = datetime.date.today()
    end_day = today - datetime.timedelta(days=m)
    for x in range(n):
        days = n - x - 1
        day = end_day - datetime.timedelta(days=days)
        date = str(day).replace('-', '')
        date_list.append(date)
    return date_list


# 判断指定路径文件是否存在
def is_exist_file(file=None):
    if os.path.exists(file):
        return True
    else:
        return False


def linux_time_to_datetime(linux_time=None):
    if linux_time:
        if len(str(linux_time)) == 13:
            linux_time = int(linux_time / 1000)
        if len(str(linux_time)) == 10:
            linux_time = time.localtime(float(linux_time))
            # my_datetime = datetime.datetime.fromtimestamp(linux_time)
            my_datetime = time.strftime('%Y-%m-%d %H:%M:%S', linux_time)
            return my_datetime
    return linux_time


# 获取当前时间（类型：datetime）
def get_datetime_now():
    datetime_now = datetime.datetime.now()
    return datetime_now


# 获取当前时间，如'2019-05-11 00:00:00'
def get_str_datetime_now():
    datetime_now = get_datetime_now()
    str_datetime_now = datetime_now.strftime("%Y-%m-%d %H:%M:%S")
    return str_datetime_now


# 获取指定位数unix时间
def get_unix_time(time_length=0):
    return str(time.time()).replace('.', '')[:time_length]


# 转浏览器cookie为键值对形式
def convert_cookies(cookies):
    if cookies:
        cookies_list = cookies.split('; ')
        cookies = {}
        for data in cookies_list:
            # (以'='切割，1为切割1次)
            key = data.split('=', 1)[0]
            value = data.split('=', 1)[1]
            cookies[key] = value
    return cookies


# 通过 cookie_jar 从 response 拿 cookie
def get_cookie_by_cookie_jar_from_response(response=None):
    cookies = {}
    if response:
        cookie_jar = CookieJar()
        cookie_jar.extract_cookies(response, response.request)
        for cookie in cookie_jar:
            cookies.update({
                cookie.name: cookie.value,
            })
    return cookies


# 建立 mongo 连接
def get_mongo_client(host=None, port=None, username=None, password=None):
    client = pymongo.MongoClient(host=host, port=port, username=username, password=password)
    return client


# 拿到单个 mongo 集合的1条数据
def get_single_mongo_data(client=None, db=None, col=None, my_query=None):
    data = client[db][col].find_one(my_query)
    return data


# 拿到单个 mongo 集合的所有数据
def get_mongo_data(client=None, db=None, col=None, my_query=None, no_timeout=False, my_sort=None):
    if my_sort:
        data = client[db][col].find(my_query, no_cursor_timeout=no_timeout).sort(my_sort)
    else:
        data = client[db][col].find(my_query, no_cursor_timeout=no_timeout)
    return data


# 拿到单个 mongo 集合的count（有筛选条件，默认为None）
def get_mongo_data_count(client=None, db=None, col=None, my_query=None):
    data = client[db][col].find(my_query).count()
    return data


# 拿到单个 mongo 集合的count（同get_mongo_data_count）
def get_mongo_col_count(client=None, db=None, col=None, my_query=None):
    data = get_mongo_data_count(client=client, db=db, col=col, my_query=my_query)
    return data


# 解析json字符串为字典
def loads_text_to_json(text=None):
    try:
        data = json.loads(text)
    except:
        data = {}
    return data


def str_time_to_linux_time(str_time):
    time_array = time.strptime(str_time, "%Y-%m-%d %H:%M:%S")
    linux_time = int(time.mktime(time_array))
    return linux_time


def get_linux_time_now():
    return int(time.time())


def get_content_by_custom_constant(response=None, url=None):
    # url = response.url
    full_domain = re.findall(r'://(.*?)/', url)[0]
    domain = remove_common_top_level_domains(domain=full_domain, common_top_level_domains=common_top_level_domains)
    domain_list = domain.split('.')
    info = match_info_by_domain(domain_list=domain_list, info_list=info_list)

    if info:
        content_xpath_list = info['content_xpath_list']
        content = get_xpath_value_result(response, xpath_list=content_xpath_list)
        return content
    return ''


def get_content_by_extractor(html=None):
    # html = response.text
    data = extractor.extract(html)
    if data:
        content = data.get('content')
        if content:
            return content
    return ''


def get_data_by_extractor(html=None):
    # html = response.text
    data = extractor.extract(html) or {}
    return data


# walk all dir
def get_pdf_file(file_pdf_path=None, check_format=None, option=False):
    all_check_path = []
    file_format = {'pdf': ['pdf'],
                   'word': ['doc', 'docx'],
                   'image': ['jpeg', 'jpg', 'png', 'gif'],
                   'vedio': ['mp4', 'flv', 'mkv', 'avi', 'mov', ],
                   'voice': ['wmv', 'mp3'], }
    for root, dirs, files in os.walk(file_pdf_path):
        for file in files:
            for detail_format in file_format.get(str(check_format)):
                if file.split('.')[-1] == detail_format:
                    pdf_all_path = os.path.join(root, file)
                    all_check_path.append(pdf_all_path)
        if not option:
            break
    return all_check_path


# 检查PDF
def check_pdf(check_format_list=None):
    error_pdf_list = []
    for pdf_path in check_format_list:
        try:
            doc = PdfFileReader(open(str(pdf_path), 'rb'))
            # print('%s----is_ok,%s' % (pdf_path, doc))

        except Exception as error:
            error_pdf_list.append(str(pdf_path))
            # print('%s----is_error,%s'% (pdf_path,error))

    return error_pdf_list


def delete_pdf(delete_pdf_list=None):
    # fo=open(str(delete_pdf_txt),'r')
    for delete_pdf in delete_pdf_list:
        # delete_pdf=delete_pdf.rstrip('\n')
        try:
            if os.path.exists(delete_pdf):
                os.remove(delete_pdf)
                print('delete success %s' % delete_pdf)

        except Exception as error:
            print(error)


# 删除无法打开的PDF
def delete_bad_pdf(file_pdf_path=None, check_format=None, option=False):
    delete_pdf(check_pdf(get_pdf_file(file_pdf_path=file_pdf_path, check_format=check_format, option=option)))


# 获取n秒前时间
def get_seconds_ago_datetime(seconds=0, date_format='%Y-%m-%d %H:%M:%S'):
    seconds = int(seconds)
    t = time.time() - seconds
    t = time.strftime(date_format, time.localtime(t))
    return t


# 获取n天前日期
def get_days_ago_date(days=0):
    today = datetime.date.today()
    days_ago_date = today - datetime.timedelta(days=days)
    return days_ago_date


# 转换"xx前"时间
def convert_n_long_ago_datetime(release_time=None):
    if release_time:

        # special
        if '今天' in release_time:
            release_time = str(release_time).replace('今天', str(get_days_ago_date(days=0)))
            return release_time

        elif '昨天' in release_time:
            release_time = str(release_time).replace('昨天', str(get_days_ago_date(days=1)))
            return release_time

        elif '前天' in release_time:
            release_time = str(release_time).replace('前天', str(get_days_ago_date(days=2)))
            return release_time

        # universal
        seconds = 0
        if '年前' in release_time:
            years = re.findall(r'(\d+)年前', release_time)
            if years:
                years = int(years[0])
                seconds = years * 365 * 24 * 60 * 60

        elif '月前' in release_time:
            months = re.findall(r'(\d+)月前', release_time)
            if months:
                months = int(months[0])
                seconds = months * 30 * 24 * 60 * 60

        elif '周前' in release_time:
            days = re.findall(r'(\d+)周前', release_time)
            if days:
                days = int(days[0])
                seconds = days * 7 * 24 * 60 * 60

        elif '天前' in release_time:
            days = re.findall(r'(\d+)天前', release_time)
            if days:
                days = int(days[0])
                seconds = days * 24 * 60 * 60

        elif '小时前' in release_time:
            hours = re.findall(r'(\d+)小时前', release_time)
            if hours:
                hours = int(hours[0])
                seconds = hours * 60 * 60

        elif '分钟前' in release_time:
            minutes = re.findall(r'(\d+)分钟前', release_time)
            if minutes:
                minutes = int(minutes[0])
                seconds = minutes * 60

        elif '秒前' in release_time:
            t_seconds = re.findall(r'(\d+)秒前', release_time)
            if t_seconds:
                seconds = int(t_seconds[0])

        if seconds != 0:
            release_time = get_seconds_ago_datetime(seconds)

    return release_time
