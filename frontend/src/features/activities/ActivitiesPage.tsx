import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { api, type ActivityListItem } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  Segmented,
  SportIcon,
  StatPod,
  fmtDuration,
  fmtHours,
  fmtNum,
  friendlyDiscipline,
} from "../../components/kit";
import { Tabs } from "../../components/Tabs";
import { localDay, shiftDay, useUnits } from "../../components/data";
export default function ActivitiesPage() {
  const { t } = useTranslation();
  const units = useUnits();
  const timezone = useUi((s) => s.me?.timezone);
  const [range, setRange] = useState("90");
  const [disc, setDisc] = useState("all");
  const end = localDay(timezone),
    start = shiftDay(end, -Number(range) + 1);
  const query = useInfiniteQuery({
    queryKey: ["activities", range, start, end],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.get<{
        items: ActivityListItem[];
        total: number;
        offset: number;
        limit: number;
      }>(
        "/activities?limit=50&offset=" +
          pageParam +
          "&start=" +
          start +
          "&end=" +
          end,
      ),
    getNextPageParam: (last) =>
      last.offset + last.items.length < last.total && last.items.length > 0
        ? last.offset + last.items.length
        : undefined,
  });
  const items = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const disciplines = [
    ...new Set(items.map((a) => a.discipline).filter((d): d is string => !!d)),
  ];
  const filtered =
    disc === "all" ? items : items.filter((a) => a.discipline === disc);
  const total = query.data?.pages[0].total ?? 0;
  const distance = filtered.filter((a) => a.distance_m != null);
  const load = filtered.filter((a) => a.training_load != null);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("activities.title")}
        subtitle={t("design.activities_sub")}
        actions={
          <Segmented
            value={range}
            onChange={(v) => {
              setRange(v);
              setDisc("all");
            }}
            options={[
              { value: "30", label: t("activities.30d") },
              { value: "90", label: t("activities.90d") },
              { value: "365", label: t("activities.12m") },
            ]}
          />
        }
      />
      <Tabs
        label={t("activities.all")}
        value={disc}
        onChange={setDisc}
        options={[
          { value: "all", label: t("activities.all") },
          ...disciplines.map((d) => ({
            value: d,
            label: friendlyDiscipline(d, t),
          })),
        ]}
      />
      {query.isLoading ? (
        <Loading />
      ) : query.isError && !query.data ? (
        <ErrorNote />
      ) : items.length === 0 ? (
        <Card>
          <Empty>{t("activities.empty")}</Empty>
        </Card>
      ) : (
        <>
          <div className="stat-row">
            <StatPod
              label={t("activities.sessions")}
              value={String(filtered.length)}
              sub={
                items.length < total
                  ? t("design.loaded_of", { count: items.length, total })
                  : t("activities.in_range")
              }
            />
            <StatPod
              label={t("activities.time_total")}
              value={fmtHours(filtered.reduce((a, b) => a + b.duration_s, 0))}
            />
            <StatPod
              label={t("activities.distance_total")}
              value={fmtNum(
                distance.length
                  ? units.distance(
                      distance.reduce((a, b) => a + b.distance_m!, 0),
                    )
                  : null,
                1,
              )}
              unit={units.distanceUnit}
            />
            <StatPod
              label={t("activities.load_total")}
              value={fmtNum(
                load.length
                  ? load.reduce((a, b) => a + b.training_load!, 0)
                  : null,
              )}
              unit={t("lab.load_points")}
            />
          </div>
          {items.length < total && (
            <p className="text-[12px] text-muted">{t("design.loaded_stats")}</p>
          )}
          <Card className="!py-0">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("design.session")}</th>
                    <th>{t("activities.duration")}</th>
                    <th className="numeric">{t("activities.distance")}</th>
                    <th className="numeric">{t("activities.elevation")}</th>
                    <th className="numeric">{t("activities.avg_hr")}</th>
                    <th className="numeric">{t("activities.avg_power")}</th>
                    <th className="numeric">{t("activities.load")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link
                          className="flex items-center gap-4"
                          to={"/app/activities/" + a.id}
                        >
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center bg-surface2">
                            <SportIcon discipline={a.discipline} size={18} />
                          </span>
                          <span>
                            <span className="text-[14px] font-medium">
                              {friendlyDiscipline(a.discipline, t)}
                            </span>
                            <span className="mt-1 block text-[12px] text-muted">
                              {new Date(a.start_time).toLocaleDateString(
                                undefined,
                                {
                                  day: "numeric",
                                  month: "short",
                                  year: "numeric",
                                  timeZone: timezone,
                                },
                              )}{" "}
                              ·{" "}
                              {new Date(a.start_time).toLocaleTimeString(
                                undefined,
                                {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                  timeZone: timezone,
                                },
                              )}
                            </span>
                            <span className="mt-1 block text-[12px] text-muted">
                              {a.sources.join(" · ")}
                            </span>
                          </span>
                        </Link>
                      </td>
                      <td>{fmtDuration(a.duration_s)}</td>
                      <td className="numeric">
                        {fmtNum(units.distance(a.distance_m), 1)}{" "}
                        <span className="text-muted">{units.distanceUnit}</span>
                      </td>
                      <td className="numeric">
                        {fmtNum(units.elevation(a.elevation_gain_m))}{" "}
                        <span className="text-muted">
                          {units.elevationUnit}
                        </span>
                      </td>
                      <td className="numeric">
                        {fmtNum(a.avg_hr)}{" "}
                        <span className="text-muted">bpm</span>
                      </td>
                      <td className="numeric">
                        {fmtNum(a.avg_power)}{" "}
                        <span className="text-muted">W</span>
                      </td>
                      <td className="numeric">
                        {fmtNum(a.training_load)}{" "}
                        <span className="text-muted">{t("lab.load_points")}</span>
                      </td>
                      <td>
                        <Link
                          to={"/app/activities/" + a.id}
                          aria-label={t("design.open_session", {
                            name: friendlyDiscipline(a.discipline, t),
                          })}
                        >
                          <ArrowUpRight size={17} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Badge>
              {t("design.loaded_of", { count: items.length, total })}
            </Badge>
            {query.hasNextPage && (
              <Button
                variant="ghost"
                disabled={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {t(
                  query.isFetchingNextPage
                    ? "common.loading"
                    : "design.load_more",
                )}
              </Button>
            )}
          </div>
          {query.isError && <ErrorNote />}
        </>
      )}
    </div>
  );
}
