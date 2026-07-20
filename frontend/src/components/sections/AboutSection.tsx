import { motion } from "framer-motion";
import { CheckCircle2, Database, Radar, Sparkles } from "lucide-react";
import { AnimatedCounter } from "@/components/AnimatedCounter";

const benefits = [
  "Данные компаний, ИП и связанные сведения из структуры ЕГР",
  "Поиск по УНП, текущему названию и историческим наименованиям",
  "Карточка компании со статусами, адресами, датами и дополнительными блоками",
  "Справочники и связанные сущности для более точной проверки данных",
];

const stats = [
  { label: "Компаний в базе", value: 1.6, suffix: "M+", decimals: 1, icon: Database },
  { label: "Доступность", value: 99.9, suffix: "%", decimals: 1, icon: Radar },
  { label: "Средний отклик", value: 120, suffix: "ms", icon: Sparkles },
];

export const AboutSection = () => {
  return (
    <section id="about" className="relative overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="absolute inset-0">
        <div className="ambient-orb-accent absolute left-[8%] top-10 h-48 w-48" />
        <div className="ambient-orb-primary absolute bottom-10 right-[10%] h-64 w-64" />
      </div>

      <div className="container relative z-10 mx-auto max-w-6xl">
        <div className="grid items-center gap-8 lg:grid-cols-[0.95fr_1.05fr] lg:gap-12">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="surface-card rounded-[2rem] p-7 sm:p-8"
          >
            <div className="eyebrow mb-5">О сервисе</div>
            <h2 className="text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
              Сервис для поиска,
              <span className="text-gradient"> проверки и просмотра данных ЕГР</span>
            </h2>

            <p className="mt-5 text-base leading-7 text-muted-foreground sm:text-lg">
              Платформа помогает быстро находить компании Беларуси, открывать
              карточки организаций, проверять базовые сведения о контрагентах и
              работать со справочниками, которые используются в данных ЕГР.
            </p>

            <div className="mt-8 space-y-4">
              {benefits.map((benefit, index) => (
                <motion.div
                  key={benefit}
                  initial={{ opacity: 0, x: -18 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.35, delay: index * 0.06 }}
                  className="flex items-start gap-3 rounded-[1.3rem] bg-background/45 px-4 py-3"
                >
                  <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary" />
                  <span className="text-sm leading-6 text-foreground sm:text-base">{benefit}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 26 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.55 }}
            className="grid gap-4"
          >
            {stats.map((stat, index) => (
              <motion.div
                key={stat.label}
                whileHover={{ y: -6 }}
                className="surface-card rounded-[1.75rem] p-6 sm:p-7"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      {stat.label}
                    </div>
                    <div className="mt-3 text-4xl font-extrabold text-gradient sm:text-5xl">
                      <AnimatedCounter
                        value={stat.value}
                        suffix={stat.suffix}
                        decimals={stat.decimals}
                      />
                    </div>
                  </div>
                  <div className="gradient-primary flex h-12 w-12 items-center justify-center rounded-2xl text-primary-foreground shadow-soft">
                    <stat.icon className="h-6 w-6" />
                  </div>
                </div>
                <div className="mt-4 text-sm leading-6 text-muted-foreground">
                  {index === 0 &&
                    "Реестр охватывает большой массив организаций, который можно быстро просматривать через единый интерфейс."}
                  {index === 1 &&
                    "Поиск, карточка компании и связанные данные доступны как единый рабочий сценарий."}
                  {index === 2 &&
                    "Быстрый отклик особенно важен, когда сервис используется для ежедневной проверки компаний и контрагентов."}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
};
