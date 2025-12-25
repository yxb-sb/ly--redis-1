from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR

# === 算法映射配置 ===
# 如果需要扩展新算法，只需在此处添加： "算法名": 模型实例
# 确保这里的键名 (Key) 与 Dispatcher 发送的算法名一致

ALGO_MAP = {
    "LinearRegression": LinearRegression(),
    "RandomForest": RandomForestRegressor(n_estimators=100, random_state=42),
    "SVM": SVR(kernel='rbf')
}