import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Card, CardHeader, Loading } from "../../components/kit";
import { ReadError } from "../../components/ReadError";

import {ProgressMetric,type SportProgressMetric} from './SportProgressMetric';
export function EnduranceMetrics({id}:{id:number}) {
 const {t}=useTranslation();const uid=useUi(s=>s.me?.user_id);
 const query=useQuery({queryKey:['endurance',uid,id],queryFn:()=>api.get<{sport:string;metrics:SportProgressMetric[]}>(`/activities/${id}/endurance`)});
 if(query.isLoading)return <Loading/>;
 const error=query.isError&&<ReadError label={t('readRecovery.retry_analysis')} stale={!!query.data} pending={query.isFetching} retry={()=>void query.refetch()}/>;
 if(!query.data)return error;
 return <Card><CardHeader title={t('athlete.metrics_'+query.data.sport)}/>{error}<p className="mb-5 text-[13px] text-muted">{t('athlete.metrics_limits')}</p><div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">{query.data.metrics.map(metric=><ProgressMetric key={metric.key} metric={metric}/>)}</div></Card>;
}
