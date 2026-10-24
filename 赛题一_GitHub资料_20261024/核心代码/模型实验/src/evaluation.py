import numpy as np
from sklearn.metrics import roc_auc_score,average_precision_score,roc_curve,brier_score_loss,log_loss
from risk_model import score,grade,logit

def metrics(y,p):
    y=np.asarray(y);p=np.asarray(p);fpr,tpr,_=roc_curve(y,p)
    slots=int(np.ceil(len(p)*.1));cut=np.sort(p)[-slots];above=p>cut;tie=p==cut
    top=y[above].sum()+(slots-above.sum())*y[tie].mean()
    bins=np.minimum((p*10).astype(int),9)
    ece=sum(np.mean(bins==k)*abs(y[bins==k].mean()-p[bins==k].mean()) for k in range(10) if np.any(bins==k))
    return {'AUC':roc_auc_score(y,p),'AP':average_precision_score(y,p),'KS':max(tpr-fpr),'Brier':brier_score_loss(y,p),'LogLoss':log_loss(y,p),'ECE':ece,'Top10Recall':top/y.sum(),'mean_pd':p.mean(),'event_rate':y.mean()}

def instability(p,q):
    d=q-p;ds=score(q)-score(p)
    return {'mean_abs_pd':np.mean(abs(d)),'p95_abs_pd':np.quantile(abs(d),.95),'max_abs_pd':np.max(abs(d)),'mean_pd_change':np.mean(d),'mean_abs_log_odds':np.mean(abs(logit(q)-logit(p))),'mean_abs_points':np.mean(abs(ds)),'p95_abs_points':np.quantile(abs(ds),.95),'grade_migration':np.mean(grade(q)!=grade(p)),'risk_increase':np.mean(d>1e-10),'risk_decrease':np.mean(d< -1e-10)}
