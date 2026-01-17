import json
import time

TASK_REGISTRY = {}

def register_task(func):
    TASK_REGISTRY[func.__name__] = func
    return func

def _get_data(r_conn):
    import numpy as np
    stream_data = r_conn.xrange("tasks_stream", min='-', max='+')
    X, y = [], []
    for _, data in stream_data:
        if data.get(b'type').decode() == 'sample':
            features = json.loads(data.get(b'feature_values').decode())
            target = float(data.get(b'target').decode())
            X.append(features)
            y.append(target)
    if not X: return None, None
    return np.array(X), np.array(y)

# === 任务定义 ===

@register_task
def simple_add(params, r_conn):
    return {"result": params.get("a", 0) + params.get("b", 0)}

@register_task
def shuffle_feature_test(params, r_conn):
    import numpy as np
    X, y = _get_data(r_conn)
    if X is None: return {"error": "No data"}
    col_idx = params.get("col_index", 0)
    if col_idx >= X.shape[1]: return {"error": "Index out of bounds"}
    
    orig_corr = np.corrcoef(X[:, col_idx], y)[0, 1]
    np.random.shuffle(X[:, col_idx])
    shuffled_corr = np.corrcoef(X[:, col_idx], y)[0, 1]
    
    return {
        "feature_idx": col_idx,
        "orig_corr": float(orig_corr),
        "shuff_corr": float(shuffled_corr),
        "diff": abs(orig_corr - shuffled_corr)
    }

@register_task
def pca_feature_extract(params, r_conn):
    from sklearn.decomposition import PCA
    X, _ = _get_data(r_conn)
    if X is None: return {"error": "No data"}
    n = params.get("n_components", 2)
    pca = PCA(n_components=n)
    pca.fit(X)
    return {
        "n_components": n,
        "variance_ratio": pca.explained_variance_ratio_.tolist()
    }

@register_task
def train_ml_model(params, r_conn):
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_squared_error
    
    X, y = _get_data(r_conn)
    if X is None: return {"error": "No data"}
    
    name = params.get("model_name")
    m_params = params.get("model_params", {})
    
    models = {"LinearRegression": LinearRegression, "Ridge": Ridge, "RandomForest": RandomForestRegressor}
    if name not in models: return {"error": f"Unknown model {name}"}
    
    clf = models[name](**m_params)
    clf.fit(X, y)
    pred = clf.predict(X)
    return {"mse": mean_squared_error(y, pred)}