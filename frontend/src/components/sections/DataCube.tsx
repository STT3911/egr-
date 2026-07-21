import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { Database, Network, ShieldAlert } from "lucide-react";

const coreLayers = Array.from({ length: 9 }, (_, index) => ({
  rotation: `${index * 20}deg`,
  opacity: 0.2 + index * 0.055,
}));

const particles = [
  { x: "18%", y: "20%", delay: "0s" },
  { x: "82%", y: "18%", delay: "-1.6s" },
  { x: "91%", y: "62%", delay: "-3.2s" },
  { x: "13%", y: "69%", delay: "-2.3s" },
  { x: "70%", y: "88%", delay: "-4.1s" },
  { x: "34%", y: "8%", delay: "-0.8s" },
];

const metrics = [
  { icon: Database, value: "ЕГР", label: "официальные данные", className: "data-cube-metric-a" },
  { icon: Network, value: "Связи", label: "между компаниями", className: "data-cube-metric-b" },
  { icon: ShieldAlert, value: "Риски", label: "важные сигналы", className: "data-cube-metric-c" },
];

export const DataCube = () => {
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    let frameId = 0;

    const updateTilt = (clientX: number, clientY: number) => {
      const bounds = stage.getBoundingClientRect();
      const normalizedX = (clientX - bounds.left) / bounds.width - 0.5;
      const normalizedY = (clientY - bounds.top) / bounds.height - 0.5;

      stage.style.setProperty("--cube-tilt-x", `${-normalizedY * 8}deg`);
      stage.style.setProperty("--cube-tilt-y", `${normalizedX * 11}deg`);
    };

    const handlePointerMove = (event: PointerEvent) => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => updateTilt(event.clientX, event.clientY));
    };

    const resetTilt = () => {
      stage.style.setProperty("--cube-tilt-x", "0deg");
      stage.style.setProperty("--cube-tilt-y", "0deg");
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        stage.dataset.visible = String(entry.isIntersecting && !document.hidden);
      },
      { threshold: 0.05 },
    );

    const handleVisibility = () => {
      stage.dataset.visible = String(!document.hidden);
    };

    stage.addEventListener("pointermove", handlePointerMove, { passive: true });
    stage.addEventListener("pointerleave", resetTilt);
    document.addEventListener("visibilitychange", handleVisibility);
    observer.observe(stage);

    return () => {
      window.cancelAnimationFrame(frameId);
      stage.removeEventListener("pointermove", handlePointerMove);
      stage.removeEventListener("pointerleave", resetTilt);
      document.removeEventListener("visibilitychange", handleVisibility);
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={stageRef} className="data-cube-stage" data-visible="true">
      <div className="data-cube-halo" aria-hidden="true" />
      <div className="data-cube-orbit data-cube-orbit-a" aria-hidden="true" />
      <div className="data-cube-orbit data-cube-orbit-b" aria-hidden="true" />

      {particles.map((particle, index) => (
        <span
          key={`${particle.x}-${particle.y}`}
          className="data-cube-particle"
          style={
            {
              "--particle-x": particle.x,
              "--particle-y": particle.y,
              "--particle-delay": particle.delay,
            } as CSSProperties
          }
          aria-hidden="true"
        >
          {index % 2 === 0 ? "+" : "·"}
        </span>
      ))}

      <div className="data-cube-tilt" aria-hidden="true">
        <div className="data-cube-spin">
          <div className="data-cube-object">
            <div className="data-cube-face data-cube-face-front" />
            <div className="data-cube-face data-cube-face-back" />
            <div className="data-cube-face data-cube-face-right" />
            <div className="data-cube-face data-cube-face-left" />
            <div className="data-cube-face data-cube-face-top" />
            <div className="data-cube-face data-cube-face-bottom" />

            <div className="data-cube-core-volume">
              {coreLayers.map((layer) => (
                <span
                  key={layer.rotation}
                  className="data-cube-core-layer"
                  style={
                    {
                      "--core-rotation": layer.rotation,
                      "--core-opacity": layer.opacity,
                    } as CSSProperties
                  }
                />
              ))}
              <span className="data-cube-core-ring data-cube-core-ring-x" />
              <span className="data-cube-core-ring data-cube-core-ring-y" />
              <span className="data-cube-core-ring data-cube-core-ring-z" />
              <span className="data-cube-core-light" />
            </div>
          </div>
        </div>
      </div>

      {metrics.map((metric) => (
        <div key={metric.value} className={`data-cube-metric ${metric.className}`}>
          <metric.icon className="h-4 w-4 text-primary" />
          <div>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
          </div>
        </div>
      ))}

      <div className="data-cube-caption">
        <span className="data-cube-caption-dot" />
        Живое досье компании
      </div>
    </div>
  );
};
