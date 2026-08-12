import { motion } from "framer-motion";
import { CheckCircle2, Database, Radar, ShieldCheck, Sparkles } from "lucide-react";

const benefits = [
  "Официальные сведения и история изменений в одном профиле",
  "Понятные связи между компаниями, адресами и контактами",
  "Сигналы, которые помогают быстрее заметить важное",
  "Готовый результат для аналитика, юриста или руководителя",
];

const stats = [
  { label: "Компаний в базе", value: "1,6 млн", icon: Database },
  { label: "Доступность сервиса", value: "99,9%", icon: Radar },
  { label: "Средний отклик", value: "120 мс", icon: Sparkles },
];

export const AboutSection = () => {
  return (
    <section id="about" className="landing-section relative scroll-mt-28 overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="ambient-orb-primary pointer-events-none absolute right-[4%] top-16 h-72 w-72" />

      <div className="container relative z-10 mx-auto max-w-7xl">
        <div className="grid items-center gap-10 lg:grid-cols-[0.92fr_1.08fr] lg:gap-16">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.5 }}
          >
            <div className="eyebrow mb-5">Почему TENDERS.BY</div>
            <h2 className="text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
              Данные становятся
              <span className="text-gradient"> ясным решением</span>
            </h2>
            <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
              Мы не просто показываем поля реестра. TENDERS.BY собирает контекст компании и помогает быстро понять, что действительно требует внимания.
            </p>

            <div className="mt-8 space-y-3">
              {benefits.map((benefit, index) => (
                <motion.div
                  key={benefit}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.35, delay: index * 0.06 }}
                  className="about-benefit"
                >
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary" />
                  <span>{benefit}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
            className="insight-panel"
          >
            <div className="insight-panel-head">
              <div className="flex items-center gap-3">
                <div className="feature-icon">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-semibold text-foreground">Business Pulse</div>
                  <div className="text-xs text-muted-foreground">Интеллектуальная сводка профиля</div>
                </div>
              </div>
              <div className="insight-status"><span /> Профиль выглядит спокойно</div>
            </div>

            <div className="insight-grid">
              <div className="risk-radar">
                <div className="risk-radar-ring risk-radar-ring-a" />
                <div className="risk-radar-ring risk-radar-ring-b" />
                <div className="risk-radar-ring risk-radar-ring-c" />
                <div className="risk-radar-core">8</div>
                <div className="risk-radar-label">Радар риска</div>
              </div>

              <div className="insight-signals">
                <div className="insight-signal">
                  <span>Уверенность данных</span>
                  <strong>87%</strong>
                  <div className="insight-bar"><i style={{ width: "87%" }} /></div>
                </div>
                <div className="insight-signal">
                  <span>Значимые связи</span>
                  <strong>3</strong>
                  <div className="insight-bar"><i style={{ width: "46%" }} /></div>
                </div>
                <div className="insight-signal insight-signal-accent">
                  <span>Сигналы внимания</span>
                  <strong>1</strong>
                  <div className="insight-bar"><i style={{ width: "24%" }} /></div>
                </div>
              </div>
            </div>

            <div className="insight-footer">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Сводка объясняет результат, а исходные данные всегда остаются доступными.
            </div>
          </motion.div>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {stats.map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: index * 0.06 }}
              className="about-stat"
            >
              <stat.icon className="h-5 w-5 text-primary" />
              <div>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
