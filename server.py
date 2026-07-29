#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import csv
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_socketio import SocketIO, emit
import threading
import queue
from io import BytesIO, StringIO
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import deque

# 设置matplotlib中文字体，防止乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'heart_rate_monitor_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 数据存储
data_queue = queue.Queue()
history_data = deque(maxlen=1000)  # 最多存储1000条历史数据
current_data = {
    'bpm': 0,
    'heartbeat': 0,
    'quality': 0,
    'spo2': 0,
    'lat': 0.0,
    'lon': 0.0,
    'gpsFix': 0,
    'sats': 0,
    'timestamp': time.time()
}

# 客户端连接管理
connected_clients = set()

# HTML模板 - 修改地图部分
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康监测系统</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>

    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: '#2563eb',
                        secondary: '#10b981',
                        danger: '#ef4444',
                        warning: '#f59e0b',
                        info: '#3b82f6'
                    },
                    fontFamily: {
                        inter: ['Inter', 'sans-serif'],
                    },
                }
            }
        }
    </script>

    <style type="text/tailwindcss">
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        @layer utilities {
            .content-auto {
                content-visibility: auto;
            }
            .glass-effect {
                backdrop-filter: blur(10px);
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            .pulse-animation {
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }
            .fade-in {
                animation: fadeIn 0.5s ease-in-out;
            }
            .slide-up {
                animation: slideUp 0.3s ease-out;
            }
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.5;
            }
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
            }
            to {
                opacity: 1;
            }
        }

        @keyframes slideUp {
            from {
                transform: translateY(20px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }

        .heartbeat-animation {
            animation: heartbeat 1.5s ease-in-out infinite;
        }

        @keyframes heartbeat {
            0% { transform: scale(1); }
            14% { transform: scale(1.3); }
            28% { transform: scale(1); }
            42% { transform: scale(1.3); }
            70% { transform: scale(1); }
        }

        .chart-container {
            position: relative;
            height: 300px;
            width: 100%;
        }

        .map-container {
            height: 400px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            background: #f8f9fa;
        }

        .stat-card {
            transition: all 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
        }

        /* 自定义地图样式 */
        .custom-marker {
            z-index: 1000;
        }

        .map-loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(255, 255, 255, 0.9);
            padding: 12px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            z-index: 1000;
        }

        .map-error {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(239, 68, 68, 0.9);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            z-index: 1000;
            text-align: center;
        }
    </style>
</head>
<body class="font-inter bg-gradient-to-br from-blue-50 via-white to-green-50 min-h-screen">
    <!-- 导航栏 -->
    <nav class="bg-white/80 backdrop-blur-md border-b border-gray-200 sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between items-center h-16">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-gradient-to-r from-primary to-secondary rounded-xl flex items-center justify-center">
                        <i class="fas fa-heartbeat text-white text-lg"></i>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-gray-900">健康监测系统</h1>
                        <p class="text-xs text-gray-500">实时心率·血氧·GPS监测</p>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <button id="exportBtn" class="bg-secondary text-white px-4 py-2 rounded-lg hover:bg-secondary/90 transition-colors">
                        <i class="fas fa-download mr-2"></i>导出数据
                    </button>
                    <button id="refreshBtn" class="bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary/90 transition-colors">
                        <i class="fas fa-bullseye mr-2"></i>刷新
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <!-- 状态指示器 -->
        <div class="mb-8">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-2xl font-bold text-gray-900">系统状态</h2>
                <div id="connectionStatus" class="flex items-center space-x-2">
                    <div id="statusIndicator" class="w-3 h-3 bg-gray-300 rounded-full"></div>
                    <span id="statusText" class="text-gray-600">等待连接...</span>
                </div>
            </div>
            <div id="lastUpdate" class="text-sm text-gray-500">
                最后更新: -
            </div>
        </div>

        <!-- 主要数据卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <!-- 心率卡片 -->
            <div id="bpmCard" class="stat-card bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-4">
                    <div class="w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center">
                        <i class="fas fa-heartbeat text-red-500 text-xl"></i>
                    </div>
                    <div id="bpmStatus" class="w-3 h-3 bg-gray-300 rounded-full"></div>
                </div>
                <h3 class="text-sm font-medium text-gray-600 mb-1">心率</h3>
                <div class="flex items-end">
                    <span id="bpmValue" class="text-3xl font-bold text-gray-900">--</span>
                    <span class="text-lg font-medium text-gray-500 ml-1">BPM</span>
                </div>
                <div id="bpmTrend" class="text-xs text-gray-500 mt-2"></div>
            </div>

            <!-- 血氧卡片 -->
            <div id="spo2Card" class="stat-card bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-4">
                    <div class="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                        <i class="fas fa-lungs text-blue-500 text-xl"></i>
                    </div>
                    <div id="spo2Status" class="w-3 h-3 bg-gray-300 rounded-full"></div>
                </div>
                <h3 class="text-sm font-medium text-gray-600 mb-1">血氧饱和度</h3>
                <div class="flex items-end">
                    <span id="spo2Value" class="text-3xl font-bold text-gray-900">--</span>
                    <span class="text-lg font-medium text-gray-500 ml-1">%</span>
                </div>
                <div id="spo2Trend" class="text-xs text-gray-500 mt-2"></div>
            </div>

            <!-- 检测状态卡片 -->
            <div id="statusCard" class="stat-card bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-4">
                    <div class="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
                        <i class="fas fa-signal text-green-500 text-xl"></i>
                    </div>
                    <div id="statusIndicatorIcon" class="w-3 h-3 bg-gray-300 rounded-full"></div>
                </div>
                <h3 class="text-sm font-medium text-gray-600 mb-1">检测状态</h3>
                <div class="flex items-end">
                    <span id="statusTextValue" class="text-xl font-bold text-gray-900">未监测</span>
                </div>
                <div id="statusDetail" class="text-xs text-gray-500 mt-2"></div>
            </div>

            <!-- GPS卡片 -->
            <div id="gpsCard" class="stat-card bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-4">
                    <div class="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
                        <i class="fas fa-map-marker-alt text-purple-500 text-xl"></i>
                    </div>
                    <div id="gpsStatus" class="w-3 h-3 bg-gray-300 rounded-full"></div>
                </div>
                <h3 class="text-sm font-medium text-gray-600 mb-1">GPS状态</h3>
                <div class="flex items-end">
                    <span id="gpsValue" class="text-xl font-bold text-gray-900">未定位</span>
                </div>
                <div id="gpsSats" class="text-xs text-gray-500 mt-2">卫星数: --</div>
            </div>
        </div>

        <!-- 图表区域 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- 心率趋势图 -->
            <div class="bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-6">
                    <h3 class="text-lg font-semibold text-gray-900">心率趋势</h3>
                    <div class="flex space-x-2">
                        <button class="time-filter-btn active px-3 py-1 text-sm rounded-full bg-primary text-white" data-range="1">1分钟</button>
                        <button class="time-filter-btn px-3 py-1 text-sm rounded-full bg-gray-200 text-gray-700" data-range="30">30分钟</button>
                        <button class="time-filter-btn px-3 py-1 text-sm rounded-full bg-gray-200 text-gray-700" data-range="60">1小时</button>
                    </div>
                </div>
                <div class="chart-container">
                    <canvas id="bpmChart"></canvas>
                </div>
            </div>

            <!-- 血氧趋势图 -->
            <div class="bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
                <div class="flex items-center justify-between mb-6">
                    <h3 class="text-lg font-semibold text-gray-900">血氧趋势</h3>
                    <div class="flex space-x-2">
                        <button class="spo2-time-filter-btn active px-3 py-1 text-sm rounded-full bg-primary text-white" data-range="1">1分钟</button>
                        <button class="spo2-time-filter-btn px-3 py-1 text-sm rounded-full bg-gray-200 text-gray-700" data-range="30">30分钟</button>
                        <button class="spo2-time-filter-btn px-3 py-1 text-sm rounded-full bg-gray-200 text-gray-700" data-range="60">1小时</button>
                    </div>
                </div>
                <div class="chart-container">
                    <canvas id="spo2Chart"></canvas>
                </div>
            </div>
        </div>

        <!-- GPS地图 -->
        <div class="bg-white rounded-2xl p-6 shadow-lg border border-gray-100 mb-8">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-lg font-semibold text-gray-900">GPS定位</h3>
                <div class="flex space-x-2">
                    <button id="centerMapBtn" class="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors">
                        <i class="fas fa-crosshairs mr-2"></i>居中地图
                    </button>
                    <button id="changeMapSourceBtn" class="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors">
                        <i class="fas fa-map mr-2"></i>切换地图源
                    </button>
                </div>
            </div>
            <div class="map-container relative">
                <div id="map" class="w-full h-full"></div>
                <div id="mapLoading" class="map-loading hidden">
                    <i class="fas fa-spinner fa-spin mr-2"></i>
                    地图加载中...
                </div>
                <div id="mapError" class="map-error hidden">
                    <i class="fas fa-exclamation-triangle mr-2"></i>
                    <div>地图加载失败</div>
                    <div class="text-xs mt-1">点击刷新按钮重试</div>
                </div>
            </div>
            <div id="gpsInfo" class="mt-4 text-sm text-gray-600">
                <p>经纬度: --, --</p>
                <p>定位精度: -- 米</p>
            </div>
        </div>

        <!-- 历史数据表格 -->
        <div class="bg-white rounded-2xl p-6 shadow-lg border border-gray-100">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-lg font-semibold text-gray-900">历史数据记录</h3>
                <div class="flex space-x-2">
                    <select id="dataFilter" class="px-3 py-2 border border-gray-300 rounded-lg text-sm">
                        <option value="all">全部数据</option>
                        <option value="valid">有效数据</option>
                        <option value="recent">最近100条</option>
                    </select>
                    <button id="clearHistory" class="px-3 py-2 text-sm bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors">
                        <i class="fas fa-trash mr-2"></i>清空
                    </button>
                </div>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="border-b border-gray-200">
                            <th class="text-left py-3 px-4 font-medium text-gray-600">时间</th>
                            <th class="text-left py-3 px-4 font-medium text-gray-600">心率</th>
                            <th class="text-left py-3 px-4 font-medium text-gray-600">血氧</th>
                            <th class="text-left py-3 px-4 font-medium text-gray-600">检测状态</th>
                            <th class="text-left py-3 px-4 font-medium text-gray-600">GPS状态</th>
                            <th class="text-left py-3 px-4 font-medium text-gray-600">卫星数</th>
                        </tr>
                    </thead>
                    <tbody id="historyTableBody">
                        <tr>
                            <td colspan="6" class="text-center py-8 text-gray-500">暂无数据</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="mt-4 text-xs text-gray-500">
                <p>共 <span id="totalCount">0</span> 条记录</p>
            </div>
        </div>
    </div>

    <!-- 加载动画 -->
    <div id="loadingOverlay" class="fixed inset-0 bg-white/80 backdrop-blur-sm z-50 hidden">
        <div class="flex items-center justify-center h-full">
            <div class="text-center">
                <div class="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                <p class="text-gray-700">正在处理数据...</p>
            </div>
        </div>
    </div>

    <script>
        // 全局变量
        let bpmChart, spo2Chart;
        let map;
        let marker;
        let currentTimeRange = 1;  // 默认1分钟
        let spo2CurrentTimeRange = 1;  // 默认1分钟
        let currentMapSource = 0;  // 0: 高德地图, 1: OpenStreetMap, 2: 百度地图
        let mapLayers = [];  // 存储所有地图图层

        // 地图源配置
        const mapSources = [
            {
                name: '高德地图',
                url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
                attribution: '© 高德地图',
                subdomains: ['1', '2', '3', '4']
            },
            {
                name: 'OpenStreetMap',
                url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                subdomains: ['a', 'b', 'c']
            },
            {
                name: '百度地图',
                url: 'http://online{s}.map.bdimg.com/onlinelabel/?qt=tile&x={x}&y={y}&z={z}&styles=pl&scaler=1&p=1',
                attribution: '© 百度地图',
                subdomains: ['01', '02', '03', '04']
            }
        ];

        // Socket.IO连接
        const socket = io();

        // 初始化
        document.addEventListener('DOMContentLoaded', function() {
            initializeCharts();
            initializeMap();
            setupEventListeners();
            updateDisplay();
        });

        // 初始化图表
        function initializeCharts() {
            // 心率图表
            const bpmCtx = document.getElementById('bpmChart').getContext('2d');
            bpmChart = new Chart(bpmCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: '心率 (BPM)',
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            min: 40,
                            max: 120,
                            ticks: {
                                stepSize: 20
                            },
                            grid: {
                                color: 'rgba(0, 0, 0, 0.1)'
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });

            // 血氧图表
            const spo2Ctx = document.getElementById('spo2Chart').getContext('2d');
            spo2Chart = new Chart(spo2Ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: '血氧 (%)',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            min: 90,
                            max: 100,
                            ticks: {
                                stepSize: 2
                            },
                            grid: {
                                color: 'rgba(0, 0, 0, 0.1)'
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });
        }

        // 初始化地图
        function initializeMap() {
            showMapLoading();

            try {
                // 创建地图实例
                map = L.map('map', {
                    zoomControl: true,
                    attributionControl: true
                }).setView([31.337146, 118.369291], 16);  // 设置为芜湖的坐标

                // 初始化所有地图图层
                mapSources.forEach((source, index) => {
                    const layer = L.tileLayer(source.url, {
                        attribution: source.attribution,
                        subdomains: source.subdomains,
                        maxZoom: 18,
                        minZoom: 3,
                        tileSize: 256
                    });
                    mapLayers.push(layer);
                });

                // 添加当前选中的地图图层
                mapLayers[currentMapSource].addTo(map);

                // 创建自定义标记
                marker = L.marker([31.337146, 118.369291], {
                    icon: L.divIcon({
                        className: 'custom-marker',
                        html: '<div class="w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-lg pulse-animation"></div>',
                        iconSize: [16, 16],
                        iconAnchor: [8, 8]
                    })
                }).addTo(map);

                marker.bindPopup('当前位置').openPopup();

                // 地图加载完成事件
                map.on('load', function() {
                    hideMapLoading();
                    console.log('地图加载完成');
                });

                // 地图瓦片加载错误处理
                map.on('tileerror', function(err) {
                    console.error('地图瓦片加载错误:', err);
                    if (currentMapSource === 0) {
                        // 如果高德地图加载失败，尝试切换到其他地图源
                        setTimeout(() => {
                            currentMapSource = 1;
                            changeMapSource();
                        }, 1000);
                    }
                });

                hideMapLoading();

            } catch (error) {
                console.error('地图初始化失败:', error);
                showMapError();
            }
        }

        // 切换地图源
        function changeMapSource() {
            showMapLoading();

            try {
                // 移除当前地图图层
                if (mapLayers[currentMapSource]) {
                    map.removeLayer(mapLayers[currentMapSource]);
                }

                // 切换到下一个地图源
                currentMapSource = (currentMapSource + 1) % mapSources.length;

                // 添加新的地图图层
                if (mapLayers[currentMapSource]) {
                    mapLayers[currentMapSource].addTo(map);

                    // 更新按钮文本
                    const btn = document.getElementById('changeMapSourceBtn');
                    btn.innerHTML = `<i class="fas fa-map mr-2"></i>切换地图源 (${mapSources[currentMapSource].name})`;

                    setTimeout(() => {
                        hideMapLoading();
                    }, 1000);
                } else {
                    hideMapLoading();
                    showMapError();
                }

            } catch (error) {
                console.error('切换地图源失败:', error);
                hideMapLoading();
                showMapError();
            }
        }

        // 显示地图加载中
        function showMapLoading() {
            document.getElementById('mapLoading').classList.remove('hidden');
            document.getElementById('mapError').classList.add('hidden');
        }

        // 隐藏地图加载中
        function hideMapLoading() {
            document.getElementById('mapLoading').classList.add('hidden');
        }

        // 显示地图错误
        function showMapError() {
            document.getElementById('mapError').classList.remove('hidden');
            document.getElementById('mapLoading').classList.add('hidden');
        }

        // 设置事件监听器
        function setupEventListeners() {
            // 时间范围切换
            document.querySelectorAll('.time-filter-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.time-filter-btn').forEach(b => {
                        b.classList.remove('active', 'bg-primary', 'text-white');
                        b.classList.add('bg-gray-200', 'text-gray-700');
                    });
                    this.classList.add('active', 'bg-primary', 'text-white');
                    this.classList.remove('bg-gray-200', 'text-gray-700');
                    currentTimeRange = parseInt(this.dataset.range);
                    updateCharts();
                });
            });

            document.querySelectorAll('.spo2-time-filter-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.spo2-time-filter-btn').forEach(b => {
                        b.classList.remove('active', 'bg-primary', 'text-white');
                        b.classList.add('bg-gray-200', 'text-gray-700');
                    });
                    this.classList.add('active', 'bg-primary', 'text-white');
                    this.classList.remove('bg-gray-200', 'text-gray-700');
                    spo2CurrentTimeRange = parseInt(this.dataset.range);
                    updateSpO2Charts();
                });
            });

            // 导出按钮
            document.getElementById('exportBtn').addEventListener('click', function() {
                showLoading();
                fetch('/export_data')
                    .then(response => response.blob())
                    .then(blob => {
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `health_data_${new Date().toISOString().slice(0,10)}.csv`;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        document.body.removeChild(a);
                        hideLoading();
                    })
                    .catch(err => {
                        console.error('导出失败:', err);
                        hideLoading();
                        alert('导出失败，请重试');
                    });
            });

            // 刷新按钮
            document.getElementById('refreshBtn').addEventListener('click', function() {
                location.reload();
            });

            // 居中地图按钮
            document.getElementById('centerMapBtn').addEventListener('click', function() {
                if (current_data.lat !== 0 && current_data.lon !== 0) {
                    map.setView([current_data.lat, current_data.lon], 16);
                } else {
                    // 如果没有GPS数据，使用默认位置（芜湖）
                    map.setView([31.337146, 118.369291], 16);
                }
            });

            // 切换地图源按钮
            document.getElementById('changeMapSourceBtn').addEventListener('click', function() {
                changeMapSource();
            });

            // 数据筛选
            document.getElementById('dataFilter').addEventListener('change', function() {
                updateHistoryTable(this.value);
            });

            // 清空历史
            document.getElementById('clearHistory').addEventListener('click', function() {
                if (confirm('确定要清空所有历史数据吗？')) {
                    fetch('/clear_history', { method: 'POST' })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateDisplay();
                            }
                        });
                }
            });
        }

        // Socket.IO事件处理
        socket.on('connect', function() {
            console.log('Connected to server');
            updateConnectionStatus(true);
        });

        socket.on('disconnect', function() {
            console.log('Disconnected from server');
            updateConnectionStatus(false);
        });

        socket.on('new_data', function(data) {
            console.log('New data received:', data);
            current_data = data;
            updateDisplay();
            updateCharts();
            updateSpO2Charts();
        });

        // 更新显示
        function updateDisplay() {
            updateMainStats();
            updateStatusIndicators();
            updateMapLocation();
            updateHistoryTable(document.getElementById('dataFilter').value);
            updateLastUpdateTime();
        }

        // 更新主要统计数据
        function updateMainStats() {
            const bpmElement = document.getElementById('bpmValue');
            const spo2Element = document.getElementById('spo2Value');
            const statusTextElement = document.getElementById('statusTextValue');
            const statusDetailElement = document.getElementById('statusDetail');
            const gpsElement = document.getElementById('gpsValue');
            const gpsSatsElement = document.getElementById('gpsSats');

            // 心率
            if (current_data.bpm > 0 && current_data.heartbeat > 0) {
                bpmElement.textContent = current_data.bpm;
                bpmElement.parentElement.classList.add('slide-up');
                setTimeout(() => bpmElement.parentElement.classList.remove('slide-up'), 300);
            } else {
                bpmElement.textContent = '--';
            }

            // 血氧
            if (current_data.spo2 > 0 && current_data.heartbeat > 0) {
                spo2Element.textContent = current_data.spo2;
                spo2Element.parentElement.classList.add('slide-up');
                setTimeout(() => spo2Element.parentElement.classList.remove('slide-up'), 300);
            } else {
                spo2Element.textContent = '--';
            }

            // 检测状态
            if (current_data.heartbeat > 0) {
                statusTextElement.textContent = '监测中';
                statusTextElement.className = 'text-xl font-bold text-green-600';

                // 显示信号质量详情
                if (current_data.quality > 0) {
                    let qualityLevel = '';
                    if (current_data.quality >= 80) qualityLevel = '优秀';
                    else if (current_data.quality >= 60) qualityLevel = '良好';
                    else if (current_data.quality >= 40) qualityLevel = '一般';
                    else qualityLevel = '较差';

                    statusDetailElement.innerHTML = `信号质量: ${current_data.quality}% (${qualityLevel})`;
                } else {
                    statusDetailElement.textContent = '信号质量: --';
                }
            } else {
                statusTextElement.textContent = '未监测';
                statusTextElement.className = 'text-xl font-bold text-gray-500';
                statusDetailElement.textContent = '请将手指放在传感器上';
            }

            // GPS
            if (current_data.gpsFix === 1) {
                gpsElement.textContent = '已定位';
                gpsSatsElement.textContent = `卫星数: ${current_data.sats}`;
            } else {
                gpsElement.textContent = '未定位';
                gpsSatsElement.textContent = '卫星数: --';
            }
        }

        // 更新状态指示器
        function updateStatusIndicators() {
            // 心率状态
            const bpmStatus = document.getElementById('bpmStatus');
            if (current_data.bpm > 0 && current_data.heartbeat > 0) {
                bpmStatus.className = 'w-3 h-3 bg-green-500 rounded-full pulse-animation';
            } else {
                bpmStatus.className = 'w-3 h-3 bg-gray-300 rounded-full';
            }

            // 血氧状态
            const spo2Status = document.getElementById('spo2Status');
            if (current_data.spo2 > 0 && current_data.heartbeat > 0) {
                spo2Status.className = 'w-3 h-3 bg-green-500 rounded-full pulse-animation';
            } else {
                spo2Status.className = 'w-3 h-3 bg-gray-300 rounded-full';
            }

            // 检测状态指示器
            const statusIndicatorIcon = document.getElementById('statusIndicatorIcon');
            if (current_data.heartbeat > 0) {
                statusIndicatorIcon.className = 'w-3 h-3 bg-green-500 rounded-full pulse-animation';
            } else {
                statusIndicatorIcon.className = 'w-3 h-3 bg-gray-300 rounded-full';
            }

            // GPS状态
            const gpsStatus = document.getElementById('gpsStatus');
            if (current_data.gpsFix === 1) {
                gpsStatus.className = 'w-3 h-3 bg-green-500 rounded-full pulse-animation';
            } else {
                gpsStatus.className = 'w-3 h-3 bg-gray-300 rounded-full';
            }
        }

        // 更新地图位置
        function updateMapLocation() {
            try {
                if (map && marker) {
                    if (current_data.gpsFix === 1 && current_data.lat !== 0 && current_data.lon !== 0) {
                        const lat = current_data.lat;
                        const lon = current_data.lon;

                        marker.setLatLng([lat, lon]);
                        marker.bindPopup(`当前位置\n${lat.toFixed(6)}, ${lon.toFixed(6)}`).openPopup();

                        document.getElementById('gpsInfo').innerHTML = `
                            <p>经纬度: ${lat.toFixed(6)}, ${lon.toFixed(6)}</p>
                            <p>定位精度: -- 米</p>
                        `;
                    } else {
                        // 使用默认位置（芜湖）
                        const defaultLat = 31.337146;
                        const defaultLng = 118.369291;

                        marker.setLatLng([defaultLat, defaultLng]);
                        marker.bindPopup(`默认位置 (芜湖)\n${defaultLat.toFixed(6)}, ${defaultLng.toFixed(6)}`).openPopup();

                        document.getElementById('gpsInfo').innerHTML = `
                            <p>经纬度: ${defaultLat.toFixed(6)}, ${defaultLng.toFixed(6)}</p>
                            <p>定位精度: -- 米</p>
                            <p class="text-xs text-yellow-600">使用默认位置，GPS未定位</p>
                        `;
                    }
                }
            } catch (error) {
                console.error('更新地图位置失败:', error);
            }
        }

        // 更新图表
        function updateCharts() {
            fetch(`/get_history?range=${currentTimeRange}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const labels = data.data.map(item => {
                            const date = new Date(item.timestamp * 1000);
                            return date.toLocaleTimeString();
                        });
                        const bpmData = data.data.map(item => item.bpm);

                        bpmChart.data.labels = labels;
                        bpmChart.data.datasets[0].data = bpmData;
                        bpmChart.update('none');
                    }
                });
        }

        // 更新血氧图表
        function updateSpO2Charts() {
            fetch(`/get_history?range=${spo2CurrentTimeRange}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const labels = data.data.map(item => {
                            const date = new Date(item.timestamp * 1000);
                            return date.toLocaleTimeString();
                        });
                        const spo2Data = data.data.map(item => item.spo2);

                        spo2Chart.data.labels = labels;
                        spo2Chart.data.datasets[0].data = spo2Data;
                        spo2Chart.update('none');
                    }
                });
        }

        // 更新历史数据表格 - 最新数据显示在上面
        function updateHistoryTable(filter = 'all') {
            fetch(`/get_history?filter=${filter}`)
                .then(response => response.json())
                .then(data => {
                    const tbody = document.getElementById('historyTableBody');
                    const totalCount = document.getElementById('totalCount');

                    if (data.success && data.data.length > 0) {
                        totalCount.textContent = data.data.length;

                        // 倒序排列，最新数据显示在上面
                        const reversedData = [...data.data].reverse();

                        tbody.innerHTML = reversedData.map(item => `
                            <tr class="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                                <td class="py-3 px-4 text-gray-600">${new Date(item.timestamp * 1000).toLocaleString()}</td>
                                <td class="py-3 px-4 font-medium ${item.bpm > 0 ? 'text-gray-900' : 'text-gray-400'}">${item.bpm || '--'}</td>
                                <td class="py-3 px-4 font-medium ${item.spo2 > 0 ? 'text-gray-900' : 'text-gray-400'}">${item.spo2 || '--'}</td>
                                <td class="py-3 px-4">
                                    <span class="px-2 py-1 text-xs rounded-full ${item.heartbeat > 0 ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}">
                                        ${item.heartbeat > 0 ? '监测中' : '未监测'}
                                    </span>
                                </td>
                                <td class="py-3 px-4">
                                    <span class="px-2 py-1 text-xs rounded-full ${item.gpsFix ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}">
                                        ${item.gpsFix ? '已定位' : '未定位'}
                                    </span>
                                </td>
                                <td class="py-3 px-4 text-gray-600">${item.sats || '--'}</td>
                            </tr>
                        `).join('');
                    } else {
                        totalCount.textContent = '0';
                        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-gray-500">暂无数据</td></tr>';
                    }
                });
        }

        // 更新连接状态
        function updateConnectionStatus(connected) {
            const indicator = document.getElementById('statusIndicator');
            const statusText = document.getElementById('statusText');

            if (connected) {
                indicator.className = 'w-3 h-3 bg-green-500 rounded-full pulse-animation';
                statusText.textContent = '已连接';
                statusText.className = 'text-green-600';
            } else {
                indicator.className = 'w-3 h-3 bg-red-500 rounded-full';
                statusText.textContent = '已断开';
                statusText.className = 'text-red-600';
            }
        }

        // 更新最后更新时间
        function updateLastUpdateTime() {
            const lastUpdateElement = document.getElementById('lastUpdate');
            const lastUpdateTime = new Date(current_data.timestamp * 1000);
            lastUpdateElement.textContent = `最后更新: ${lastUpdateTime.toLocaleString()}`;
        }

        // 显示加载动画
        function showLoading() {
            document.getElementById('loadingOverlay').classList.remove('hidden');
        }

        // 隐藏加载动画
        function hideLoading() {
            document.getElementById('loadingOverlay').classList.add('hidden');
        }

        // 定期刷新数据
        setInterval(updateDisplay, 5000);
    </script>
</body>
</html>
'''


def save_plot_to_bytes(plt):
    """保存matplotlib图表到字节流"""
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    buf.seek(0)
    return buf


@app.route('/heartrate', methods=['GET'])
def heartrate():
    """接收心率数据"""
    try:
        # 获取请求参数
        bpm = int(request.args.get('bpm', 0))
        heartbeat = int(request.args.get('heartbeat', 0))
        quality = int(request.args.get('quality', 0))
        spo2 = int(request.args.get('spo2', 0))
        lat = float(request.args.get('lat', 0.0))
        lon = float(request.args.get('lon', 0.0))
        gpsFix = int(request.args.get('gpsFix', 0))
        sats = int(request.args.get('sats', 0))

        # 创建数据对象
        data = {
            'bpm': bpm,
            'heartbeat': heartbeat,
            'quality': quality,
            'spo2': spo2,
            'lat': lat,
            'lon': lon,
            'gpsFix': gpsFix,
            'sats': sats,
            'timestamp': time.time()
        }

        # 更新当前数据
        global current_data
        current_data = data

        # 添加到历史数据
        history_data.append(data.copy())

        # 发送到所有连接的客户端
        socketio.emit('new_data', data)

        print(
            f"Received data: BPM={bpm}, SpO2={spo2}, Quality={quality}, GPS={gpsFix}, Time={datetime.fromtimestamp(data['timestamp'])}")

        return jsonify({'status': 'success', 'message': 'Data received'})
    except Exception as e:
        print(f"Error processing data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/')
def index():
    """主页面"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/get_history')
def get_history():
    """获取历史数据"""
    try:
        range_minutes = request.args.get('range', type=int)
        filter_type = request.args.get('filter', 'all')

        # 获取时间范围数据
        if range_minutes:
            cutoff_time = time.time() - (range_minutes * 60)
            filtered_data = [item for item in history_data if item['timestamp'] >= cutoff_time]
        else:
            filtered_data = list(history_data)

        # 应用筛选
        if filter_type == 'valid':
            filtered_data = [item for item in filtered_data if item['bpm'] > 0 and item['spo2'] > 0]
        elif filter_type == 'recent' and len(filtered_data) > 100:
            filtered_data = filtered_data[-100:]

        return jsonify({
            'success': True,
            'data': filtered_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/export_data')
def export_data():
    """导出数据为CSV"""
    try:
        # 创建CSV文件
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'timestamp', 'bpm', 'heartbeat', 'quality', 'spo2',
            'lat', 'lon', 'gpsFix', 'sats'
        ])

        writer.writeheader()
        for item in history_data:
            # 转换时间戳为可读格式
            item_copy = item.copy()
            item_copy['timestamp'] = datetime.fromtimestamp(item['timestamp']).isoformat()
            writer.writerow(item_copy)

        output.seek(0)
        return send_file(
            BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'health_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/clear_history', methods=['POST'])
def clear_history():
    """清空历史数据"""
    try:
        history_data.clear()
        return jsonify({'success': True, 'message': 'History cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    global connected_clients
    connected_clients.add(request.sid)
    print(f"Client connected: {request.sid}")

    # 发送当前数据给新连接的客户端
    if current_data:
        emit('new_data', current_data)


@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    global connected_clients
    if request.sid in connected_clients:
        connected_clients.remove(request.sid)
    print(f"Client disconnected: {request.sid}")


def data_processor():
    """数据处理器线程"""
    while True:
        try:
            # 从队列获取数据并处理
            if not data_queue.empty():
                data = data_queue.get()
                # 这里可以添加数据处理逻辑
                pass
        except Exception as e:
            print(f"Data processor error: {e}")
        time.sleep(1)


if __name__ == '__main__':
    # 启动数据处理器线程
    processor_thread = threading.Thread(target=data_processor, daemon=True)
    processor_thread.start()

    print("健康监测服务器启动中...")
    print("访问 http://localhost:5000 查看监测界面")
    print("数据接收端点: http://localhost:5000/heartrate")

    # 启动服务器 - 添加allow_unsafe_werkzeug=True参数
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)