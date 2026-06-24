import React, { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MapPin, ExternalLink } from "lucide-react";
import { geocodeCompany } from "@/lib/api";

/**
 * Карта местоположения компании на Яндекс.Картах.
 *
 * Координаты:
 *  1) если в профиле уже есть lat/lon (геокодинг через OSM, хранится в БД) —
 *     просто рисуем точку, геокодер Яндекса НЕ дёргаем (лимит не тратится);
 *  2) если координат ещё нет — фолбэк: геокодим адрес "на лету" через JS API
 *     Яндекса и сразу показываем (результат не сохраняем — это требование
 *     бесплатной лицензии Яндекса). Лимит JS-геокодера — 25k запросов/сутки.
 *
 * Сама отрисовка карты в любом случае требует ключ JS API
 * (VITE_YANDEX_MAPS_API_KEY). Нет ключа или нет ни координат, ни адреса —
 * компонент ничего не рендерит.
 */

const YANDEX_API_KEY = import.meta.env.VITE_YANDEX_MAPS_API_KEY as string | undefined;

// Загрузчик скрипта Яндекс.Карт. Грузим один раз на всё приложение.
let ymapsPromise: Promise<any> | null = null;

function loadYmaps(apiKey: string): Promise<any> {
  if (ymapsPromise) return ymapsPromise;

  ymapsPromise = new Promise((resolve, reject) => {
    const w = window as any;
    if (w.ymaps && typeof w.ymaps.ready === "function") {
      w.ymaps.ready(() => resolve(w.ymaps));
      return;
    }
    const script = document.createElement("script");
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(apiKey)}&lang=ru_RU`;
    script.async = true;
    script.onload = () => w.ymaps.ready(() => resolve(w.ymaps));
    script.onerror = () => {
      ymapsPromise = null;
      reject(new Error("Не удалось загрузить Яндекс.Карты"));
    };
    document.head.appendChild(script);
  });

  return ymapsPromise;
}

type MapStatus = "loading" | "ready" | "notfound" | "error";

interface CompanyMapProps {
  address?: string;
  name?: string;
  /** УНП — нужен для ленивого геокодинга через бэкенд (OSM), если координат ещё нет. */
  unp?: string;
  /** Готовые координаты из БД (геокодинг через OSM). Если заданы — геокодер не дёргаем. */
  lat?: number | null;
  lon?: number | null;
}

export const CompanyMap = ({ address, name, unp, lat, lon }: CompanyMapProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const [status, setStatus] = useState<MapStatus>("loading");

  const hasStoredCoords =
    typeof lat === "number" && typeof lon === "number" && !Number.isNaN(lat) && !Number.isNaN(lon);

  // Подсказываем геокодеру страну, если её нет в адресе (адреса ЕГР/ГРП
  // приходят уже без "Республика Беларусь").
  const query = address ? (/беларус/i.test(address) ? address : `Беларусь, ${address}`) : "";
  const label = name || address || "";

  useEffect(() => {
    if (!YANDEX_API_KEY || (!hasStoredCoords && !address)) return;

    let cancelled = false;
    setStatus("loading");

    const drawAt = (ymaps: any, coords: [number, number]) => {
      if (cancelled || !containerRef.current) return;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
      const map = new ymaps.Map(containerRef.current, {
        center: coords,
        zoom: 16,
        controls: ["zoomControl", "fullscreenControl"],
      });
      const placemark = new ymaps.Placemark(
        coords,
        { balloonContent: label, hintContent: label },
        { preset: "islands#redDotIcon" }
      );
      map.geoObjects.add(placemark);
      mapRef.current = map;
      setStatus("ready");
    };

    const run = async () => {
      let coords: [number, number] | null = hasStoredCoords
        ? [lat as number, lon as number]
        : null;

      // Готовых координат нет — просим бэкенд геокоднуть через OSM и закэшировать в БД.
      if (!coords && unp) {
        try {
          const g = await geocodeCompany(unp);
          if (typeof g.latitude === "number" && typeof g.longitude === "number") {
            coords = [g.latitude, g.longitude];
          }
        } catch {
          /* падение бэкенда не критично — ниже фолбэк на геокод Яндексом */
        }
        if (cancelled) return;
      }

      const ymaps = await loadYmaps(YANDEX_API_KEY);
      if (cancelled || !containerRef.current) return;

      if (coords) {
        drawAt(ymaps, coords);
        return;
      }

      // Совсем нет координат — последний фолбэк: геокод Яндексом на лету (не сохраняем).
      if (query) {
        const res = await ymaps.geocode(query, { results: 1 });
        if (cancelled) return;
        const obj = res.geoObjects.get(0);
        if (!obj) {
          setStatus("notfound");
          return;
        }
        drawAt(ymaps, obj.geometry.getCoordinates());
        return;
      }
      setStatus("notfound");
    };

    run().catch(() => {
      if (!cancelled) setStatus("error");
    });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, [hasStoredCoords, lat, lon, query, address, label, unp]);

  // Фича выключена (нет ключа) или нечего показывать — не рендерим секцию.
  if (!YANDEX_API_KEY || (!hasStoredCoords && !address)) return null;

  const yandexSearchUrl = `https://yandex.ru/maps/?text=${encodeURIComponent(query || label)}`;

  return (
    <Card className="glass shadow-card hover:shadow-glow transition-all duration-300 border-secondary/20">
      <CardHeader
        className="rounded-t-lg"
        style={{
          background: "linear-gradient(90deg, hsl(var(--secondary) / 0.1) 0%, hsl(var(--primary) / 0.1) 100%)",
        }}
      >
        <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
          <MapPin className="w-5 h-5 text-secondary" />
          Местоположение на карте
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 sm:p-6">
        <div className="relative w-full h-64 sm:h-80 rounded-lg overflow-hidden border border-border/40">
          <div ref={containerRef} className="absolute inset-0 w-full h-full" />

          {status === "loading" && (
            <div className="absolute inset-0 flex items-center justify-center bg-muted/40 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-2 text-muted-foreground text-sm">
                <div className="w-6 h-6 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
                <span>Загрузка карты…</span>
              </div>
            </div>
          )}

          {(status === "notfound" || status === "error") && (
            <div className="absolute inset-0 flex items-center justify-center bg-muted/40 backdrop-blur-sm p-4">
              <div className="flex flex-col items-center gap-2 text-center text-sm text-muted-foreground">
                <MapPin className="w-6 h-6 opacity-60" />
                <span>
                  {status === "notfound"
                    ? "Не удалось определить точку по адресу"
                    : "Карта недоступна"}
                </span>
                <a
                  href={yandexSearchUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-secondary hover:underline"
                >
                  Открыть в Яндекс.Картах
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>
          )}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{address}</p>
      </CardContent>
    </Card>
  );
};

export default CompanyMap;
