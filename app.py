from flask import Flask, render_template, request, jsonify
import pandas as pd
import time
from math import radians, sin, cos, sqrt, atan2
import time
import numpy as np
from sklearn.neighbors import KNeighborsClassifier
import csv
app = Flask(__name__)
from azure.cosmos import CosmosClient, PartitionKey, cosmos_client
from azure.cosmos.exceptions import CosmosResourceNotFoundError
import redis
import json
# the "Primary connection string" in the "Access keys"
redis_passwd = "IftRxwH0J4i8qKhuqRwvU79NJT8jTZy7lAzCaAZJIlE="
redis_host = "zzredis.redis.cache.windows.net"
cache = redis.StrictRedis(
            host=redis_host, port=6380,
            db=0, password=redis_passwd,
            ssl=True,
        )

if cache.ping():
    print("pong")
# DB_CONN_STR = "AccountEndpoint=https://76001.documents.azure.com:443/;AccountKey=LMGe4CaKJToXlX5crrkaTGRPpWnkLmFYklRnVdm6zmUilwweTvS9ni8zvPN6zBsH8ZthkjSuGo9pACDbccUHYA=="
# db_client = CosmosClient.from_connection_string(conn_str=DB_CONN_STR)
# database = db_client.get_database_client("tutorial")

DB_CONN_STR = "AccountEndpoint=https://tutorial-uta-cse6332.documents.azure.com:443/;AccountKey=fSDt8pk5P1EH0NlvfiolgZF332ILOkKhMdLY6iMS2yjVqdpWx4XtnVgBoJBCBaHA8PIHnAbFY4N9ACDbMdwaEw==;"
db_client = CosmosClient.from_connection_string(conn_str=DB_CONN_STR)
database = db_client.get_database_client("tutorial")
amazon_reviews_container = database.get_container_client('reviews')
us_cities_container = database.get_container_client('us_cities')


app = Flask(__name__)
def fetch_data(city_name = None, include_header = False, exact_match = False):
    # return fetch_database(city_name=city_name, include_header = include_header, exact_match = exact_match)
    with open("us-cities.csv") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=',', quotechar='|')
        row_id = -1
        wanted_data = []
        for row in csvreader:
            row_id += 1
            if row_id == 0 and not include_header:
                continue
            line = []
            col_id = -1
            is_wanted_row = False
            if city_name is None:
                is_wanted_row = True
            for raw_col in row:
                col_id += 1
                col = raw_col.replace('"', '')
                line.append( col )
                if col_id == 0 and city_name is not None:
                    if not exact_match and city_name.lower() in col.lower():
                        is_wanted_row = True
                    elif exact_match and city_name.lower() == col.lower():
                        is_wanted_row = True
            if is_wanted_row:
                if row_id > 0:
                    line.insert(0, "{}".format(row_id))
                else:
                    line.insert(0, "")
                wanted_data.append(line)
    return wanted_data

def fetch_data_review(city_name = None, include_header = False, exact_match = False):
    # return fetch_database(city_name=city_name, include_header = include_header, exact_match = exact_match)
    with open("newre.csv") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=',', quotechar='|')
        row_id = -1
        wanted_data = []
        for row in csvreader:
            row_id += 1
            if row_id == 0 and not include_header:
                continue
            line = []
            col_id = -1
            is_wanted_row = False
            if city_name is None:
                is_wanted_row = True
            for raw_col in row:
                col_id += 1
                col = raw_col.replace('"', '')
                line.append( col )
                if col_id == 0 and city_name is not None:
                    if not exact_match and city_name.lower() in col.lower():
                        is_wanted_row = True
                    elif exact_match and city_name.lower() == col.lower():
                        is_wanted_row = True
            if is_wanted_row:
                if row_id > 0:
                    line.insert(0, "{}".format(row_id))
                else:
                    line.insert(0, "")
                wanted_data.append(line)
    return wanted_data

def fetch_database_us_cities(container, city_name=None, include_header=False, exact_match=False):
    """
    根据city取数据
    :param city_name: city属性，如果为None，则取所有
    :param include_header:
    :param exact_match: 完全匹配 False: 模糊匹配
    :return:
    """
    QUERY = "SELECT * from us_cities"
    params = None
    if city_name is not None:
        QUERY = "SELECT * FROM us_cities p WHERE p.city is not @city_name"
        params = [dict(name="@city_name", value=city_name)]
        if not exact_match:
            QUERY = "SELECT * FROM us_cities p WHERE p.city not like @city_name"

    headers = ["city", "lat", "lng", "country", "state", "population"]
    result = []

    # quickly fetch the result if it already in the cache
    if cache.exists(QUERY):
        result = json.loads(cache.get(QUERY).decode())
        print("cache hit: [{}]".format(QUERY))

    else:
        row_id = 0
        for item in container.query_items(
                query=QUERY, parameters=params, enable_cross_partition_query=True,
        ):
            row_id += 1
            line = [str(row_id)]
            for col in headers:
                line.append(item[col])
            result.append(line)

        # cache the result for future queries
        cache.set(QUERY, json.dumps(result))
        print("cache miss: [{}]".format(QUERY))

    if include_header:
        line = [x for x in headers]
        line.insert(0, "")
        result.insert(0, line)

    return result

def fetch_database_amazon_reviews(container, city_name=None, include_header=False, exact_match=False):
    global Q12_redis
    """
    根据city取数据
    :param city_name: city属性，如果为None，则取所有
    :param include_header:
    :param exact_match: 完全匹配 False: 模糊匹配
    :return:
    """
    QUERY = "SELECT * from reviews"
    params = None
    if city_name is not None:
        QUERY = "SELECT * FROM reviews p WHERE p.city is not @city_name"
        params = [dict(name="@city_name", value=city_name)]
        if not exact_match:
            QUERY = "SELECT * FROM reviews p WHERE p.city not like @city_name"

    headers = ["score", "city", "title", "review"]
    result = []

    # quickly fetch the result if it already in the cache
    if cache.exists(QUERY):

        Q12_redis = "Yes"
        result = json.loads(cache.get(QUERY).decode())
        print("cache hit: [{}]".format(QUERY))

    else:
        print("no redis")
        Q12_redis = "No"
        row_id = 0
        for item in container.query_items(
                query=QUERY, parameters=params, enable_cross_partition_query=True,
        ):
            row_id += 1
            line = [str(row_id)]
            for col in headers:
                line.append(item[col])
            result.append(line)

        # cache the result for future queries
        cache.set(QUERY, json.dumps(result))
        print("cache miss: [{}]".format(QUERY))

    if include_header:
        line = [x for x in headers]
        line.insert(0, "")
        result.insert(0, line)

    return result

def fetch_data_us_cities(container, city_name=None, include_header=False, exact_match=False):
    return fetch_database_us_cities(container, city_name=city_name, include_header=include_header,
                                    exact_match=exact_match)
    with open("us-cities.csv") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=',', quotechar='|')
        row_id = -1
        wanted_data = []
        for row in csvreader:
            row_id += 1
            if row_id == 0 and not include_header:
                continue
            line = []
            col_id = -1
            is_wanted_row = False
            if city_name is None:
                is_wanted_row = True
            for raw_col in row:
                col_id += 1
                col = raw_col.replace('"', '')
                line.append(col)
                if col_id == 0 and city_name is not None:
                    if not exact_match and city_name.lower() in col.lower():
                        is_wanted_row = True
                    elif exact_match and city_name.lower() == col.lower():
                        is_wanted_row = True
            if is_wanted_row:
                if row_id > 0:
                    line.insert(0, "{}".format(row_id))
                else:
                    line.insert(0, "")
                wanted_data.append(line)
    return wanted_data

def fetch_data_amazon_reviews(container, city_name=None, include_header=False, exact_match=False):
    return fetch_database_amazon_reviews(container, city_name=city_name, include_header=include_header,
                                         exact_match=exact_match)
    with open("newre.csv") as csvfile:
        csvreader = csv.reader(csvfile, delimiter=',', quotechar='|')
        row_id = -1
        wanted_data = []
        for row in csvreader:
            row_id += 1
            if row_id == 0 and not include_header:
                continue
            line = []
            col_id = -1
            is_wanted_row = False
            if city_name is None:
                is_wanted_row = True
            for raw_col in row:
                col_id += 1
                col = raw_col.replace('"', '')
                line.append( col )
                if col_id == 0 and city_name is not None:
                    if not exact_match and city_name.lower() in col.lower():
                        is_wanted_row = True
                    elif exact_match and city_name.lower() == col.lower():
                        is_wanted_row = True
            if is_wanted_row:
                if row_id > 0:
                    line.insert(0, "{}".format(row_id))
                else:
                    line.insert(0, "")
                wanted_data.append(line)
    return wanted_data


# 读取城市数据
city_data = pd.read_csv('us-cities2.csv')
review_data = pd.read_csv('newre.csv')

# 每页城市数
cities_per_page = 100

def haversine(lat1, lon1, lat2, lon2):
    # 将经纬度从度数转换为弧度
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine公式计算距离
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    radius_of_earth = 6371  # 地球半径（单位：公里）

    # 计算距离（单位：千米）
    distance = radius_of_earth * c

    return distance

def calculate_distances(target_city, target_state):
    # 查询城市距离并计算响应时间
    start_time = time.time()

    # 初始化结果列表
    city_distances = []

    # 获取目标城市的经纬度
    target_city_data = city_data[(city_data['city'] == target_city) & (city_data['state'] == target_state)]
    if not target_city_data.empty:
        target_lat = float(target_city_data['lat'])
        target_lng = float(target_city_data['lng'])

        # 计算目标城市与其他城市的距离
        for _, city in city_data.iterrows():
            lat = float(city['lat'])
            lng = float(city['lng'])
            distance = haversine(target_lat, target_lng, lat, lng)
            city_distances.append(distance)

    response_time = int((time.time() - start_time) * 1000)  # 计算响应时间（毫秒）
    return city_distances, response_time

def calculate_average_scores(target_city, target_state):
    # 计算平均评分和响应时间
    start_time = time.time()

    # 初始化结果列表
    city_scores = []

    # 获取目标城市的经纬度
    target_city_data = city_data[(city_data['city'] == target_city) & (city_data['state'] == target_state)]
    if not target_city_data.empty:
        target_lat = float(target_city_data['lat'])
        target_lng = float(target_city_data['lng'])

        # 计算目标城市与其他城市的距离和平均评分
        for _, city in city_data.iterrows():
            lat = float(city['lat'])
            lng = float(city['lng'])
            distance = haversine(target_lat, target_lng, lat, lng)

            # 过滤当前城市的评分数据
            city_reviews = review_data[review_data['city'] == city['city']]

            # 计算当前城市的平均评分
            average_score = city_reviews['score'].mean() if not city_reviews.empty else 0

            city_scores.append({'city': city['city'], 'distance': distance, 'average_score': average_score})

    # 按距离升序排序城市
    city_scores.sort(key=lambda x: x['distance'])

    response_time = int((time.time() - start_time) * 1000)  # 响应时间（毫秒）
    return city_scores, response_time


@app.route('/zzm', methods=['GET', 'POST'])
def zzm():
    if request.method == 'POST':
        city_name = request.form['city']
        state_name = request.form['country']

        # 计算平均评分
        scores, response_time = calculate_average_scores(city_name, state_name)

        # 将数据转换为JSON格式
        data = json.dumps({'scores': scores, 'response_time': response_time})
        return render_template('index_review.html', data=data)

    return render_template('index_review.html', data=None)

@app.route('/zxc', methods=['GET', 'POST'])
def zxc():
    if request.method == 'POST':
        city_name = request.form['city']
        state_name = request.form['state']

        # 计算城市距离
        distances, response_time = calculate_distances(city_name, state_name)

        # 将数据转换为JSON格式
        data = json.dumps({'distances': distances, 'response_time': response_time})
        return render_template('zxc.html', data=data)

    return render_template('zxc.html', data=None)

@app.route('/stat/knn_reviews', methods=['GET'])
def knn_reviews_stat():
    start_time = time.time()

    # 获取查询参数
    num_classes = int(request.args.get('classes', 6))
    k_param = int(request.args.get('k', 3))
    words_limit = int(request.args.get('words', 10))

    # 获取所有城市的坐标和评分数据
    print("获取城市信息中。。。")
    cities_items = fetch_database_us_cities(us_cities_container)
    print("获取评分信息中。。。")
    reviews_items = fetch_data_amazon_reviews(amazon_reviews_container)
    print("获取信息完成！")

    # reviews_items只要前1000条
    reviews_items = reviews_items[:1000]

    # 创建城市数组
    cities = [{'city': item[1], 'x': float(item[2]), 'y': float(item[3]), 'population': float(item[-1])} for item in
              cities_items]

    # 创建评分数组
    reviews = [{'city': item[2], 'score': float(item[1]), 'review': item[-1]} for item in reviews_items]

    # 获取训练集的 x 和 y 坐标
    train_data = np.array([[city['x'], city['y']] for city in cities[:num_classes]])
    # 获取预测集的 x 和 y 坐标
    predict_data = np.array([[city['x'], city['y']] for city in cities[num_classes:]])
    # 生成训练集标签
    train_labels = [i for i, _ in enumerate(range(num_classes))]

    # 使用 KNN 聚类算法, p=2为欧式距离
    knn = KNeighborsClassifier(n_neighbors=k_param, p=2).fit(train_data, train_labels)
    predict_labels = knn.predict(predict_data)
    print("聚类完成！")
    # 合并训练集和测试集的标签
    labels = np.concatenate((train_labels, predict_labels))
    # 初始化结果字典
    result = {"clusters": []}

    # 处理每个聚类
    for i in range(num_classes):
        print("处理第{}个聚类".format(i))
        # 获取该类别的城市
        cities_in_class = [cities[j] for j in range(len(cities)) if labels[j] == i]
        scores_in_class = [score['score'] for score in reviews if
                           score['city'] in [city['city'] for city in cities_in_class]]

        # 计算权重
        weights = [city['population'] / sum([city['population'] for city in cities_in_class])
                   for city in cities_in_class]

        # 计算加权平均分数
        weighted_avg_score = sum([score * weight for score, weight in zip(scores_in_class, weights)])

        # 找到类别中心点, 训练集中的城市即为中心城市
        # center_city = cities[i]
        center_city_coordinates = np.median(np.array([[city['x'], city['y']] for city in cities_in_class]), axis=0)
        center_city_coordinates = {'x': center_city_coordinates[0], 'y': center_city_coordinates[1]}

        # 找到最接近中心坐标的城市
        closest_city = min(cities_in_class, key=lambda city: np.sqrt(
            (city['x'] - center_city_coordinates['x']) ** 2 + (city['y'] - center_city_coordinates['y']) ** 2))
        center_city = closest_city['city']

        # 获取该类别的评论
        reviews_in_class = [review['review'] for review in reviews if
                            review['city'] in [city['city'] for city in cities_in_class]]

        # 处理评论，计算单词频率
        all_text = ' '.join(reviews_in_class).lower()
        words = all_text.split()
        # 去除停用词
        with open("stopwords.txt", "r") as stopword_file:
            stopwords = set(stopword_file.read().split())
        # 处理评论，去除停用词
        words = [word for word in words if word not in stopwords]
        word_counts = {word: words.count(word) for word in set(words)}

        # 按频率降序排序
        sorted_word_counts = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

        # 截取指定数量的单词
        top_words = [{"term": term, "popularity": count} for term, count in sorted_word_counts[:words_limit]]

        # 将结果添加到返回字典中
        result["clusters"].append({
            "center_city": center_city,
            "cities_in_class": cities_in_class,
            "top_words": top_words,
            "weighted_avg_score": weighted_avg_score
        })

    # 计算处理时间
    processing_time = round((time.time() - start_time) * 1000, 2)
    result["processing_time"] = processing_time
    result["redisq12"] = 11

    return jsonify(result)

@app.route('/stat/knn_reviews2', methods=['GET'])
def knn_reviews_stat2():
    start_time = time.time()

    # 获取查询参数
    num_classes = int(request.args.get('classes', 5))
    k_param = int(request.args.get('k', 2))
    words_limit = int(request.args.get('words', 5))

    # 获取所有城市的坐标和评分数据
    print("获取城市信息中。。。")
    cities_items = fetch_database_us_cities(us_cities_container)
    print("获取评分信息中。。。")
    reviews_items = fetch_data_review()
    print("获取信息完成！")

    # reviews_items只要前1000条
    reviews_items = reviews_items[:1000]

    # 创建城市数组
    cities = [{'city': item[1], 'x': float(item[2]), 'y': float(item[3]), 'population': float(item[-1])} for item in
              cities_items]

    # 创建评分数组
    reviews = [{'city': item[2], 'score': float(item[1]), 'review': item[-1]} for item in reviews_items]

    # 获取训练集的 x 和 y 坐标
    train_data = np.array([[city['x'], city['y']] for city in cities[:num_classes]])
    # 获取预测集的 x 和 y 坐标
    predict_data = np.array([[city['x'], city['y']] for city in cities[num_classes:]])
    # 生成训练集标签
    train_labels = [i for i, _ in enumerate(range(num_classes))]

    # 使用 KNN 聚类算法, p=2为欧式距离
    knn = KNeighborsClassifier(n_neighbors=k_param, p=2).fit(train_data, train_labels)
    predict_labels = knn.predict(predict_data)
    print("聚类完成！")
    # 合并训练集和测试集的标签
    labels = np.concatenate((train_labels, predict_labels))
    # 初始化结果字典
    result = {"clusters": []}

    # 处理每个聚类
    for i in range(num_classes):
        print("处理第{}个聚类".format(i))
        # 获取该类别的城市
        cities_in_class = [cities[j] for j in range(len(cities)) if labels[j] == i]
        scores_in_class = [score['score'] for score in reviews if
                           score['city'] in [city['city'] for city in cities_in_class]]

        # 计算权重
        weights = [city['population'] / sum([city['population'] for city in cities_in_class])
                   for city in cities_in_class]

        # 计算加权平均分数
        weighted_avg_score = sum([score * weight for score, weight in zip(scores_in_class, weights)])

        # 找到类别中心点, 训练集中的城市即为中心城市
        # center_city = cities[i]
        center_city_coordinates = np.median(np.array([[city['x'], city['y']] for city in cities_in_class]), axis=0)
        center_city_coordinates = {'x': center_city_coordinates[0], 'y': center_city_coordinates[1]}

        # 找到最接近中心坐标的城市
        closest_city = min(cities_in_class, key=lambda city: np.sqrt(
            (city['x'] - center_city_coordinates['x']) ** 2 + (city['y'] - center_city_coordinates['y']) ** 2))
        center_city = closest_city['city']

        # 获取该类别的评论
        reviews_in_class = [review['review'] for review in reviews if
                            review['city'] in [city['city'] for city in cities_in_class]]

        # 处理评论，计算单词频率
        all_text = ' '.join(reviews_in_class).lower()
        words = all_text.split()
        # 去除停用词
        with open("stopwords.txt", "r") as stopword_file:
            stopwords = set(stopword_file.read().split())
        # 处理评论，去除停用词
        words = [word for word in words if word not in stopwords]
        word_counts = {word: words.count(word) for word in set(words)}

        # 按频率降序排序
        sorted_word_counts = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

        # 截取指定数量的单词
        top_words = [{"term": term, "popularity": count} for term, count in sorted_word_counts[:words_limit]]

        # 将结果添加到返回字典中
        result["clusters"].append({
            "center_city": center_city,
            "cities_in_class": cities_in_class,
            "top_words": top_words,
            "weighted_avg_score": weighted_avg_score
        })

    # 计算处理时间
    processing_time = round((time.time() - start_time) * 1000, 2)
    result["processing_time"] = processing_time
    result["redisq12"] = 11

    return jsonify(result)
# Run the app
@app.route("/", methods=['GET'])
def index():
    return render_template(
        'hh.html'
    )
if __name__ == '__main__':
    app.run(debug=True)