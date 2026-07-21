import { motion } from "framer-motion";
import {
  ArrowRight,
  Building2,
  FileDown,
  Network,
  Search,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

const capabilities = [
  {
    icon: Building2,
    number: "01",
    title: "Полная карточка",
    description: "Статус, адреса, регистрация и история названий без переходов между источниками.",
  },
  {
    icon: Network,
    number: "02",
    title: "Карта связей",
    description: "Связанные компании и общие контакты превращаются в понятную структуру.",
  },
  {
    icon: ShieldAlert,
    number: "03",
    title: "Сигналы риска",
    description: "Важные события не теряются в массиве исходных данных.",
  },
  {
    icon: FileDown,
    number: "04",
    title: "Готовое досье",
    description: "Собирайте результат проверки в единый отчёт для команды или сделки.",
  },
];

const steps = [
  { label: "Запрос", value: "Название или УНП" },
  { label: "Сбор", value: "Официальные источники" },
  { label: "Анализ", value: "Связи и события" },
  { label: "Решение", value: "Понятное досье" },
];

export const FeaturesSection = () => {
  return (
    <section id="features" className="landing-section relative scroll-mt-28 overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="absolute inset-0 pointer-events-none registry-grid opacity-20" />

      <div className="container relative z-10 mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mb-12 grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end"
        >
          <div className="max-w-3xl">
            <div className="eyebrow mb-5">Возможности</div>
            <h2 className="text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
              От первого запроса
              <span className="text-gradient"> до уверенного решения</span>
            </h2>
          </div>
          <p className="max-w-xl text-base leading-7 text-muted-foreground lg:max-w-sm">
            Tendex собирает разрозненные сведения в один рабочий сценарий проверки.
          </p>
        </motion.div>

        <div className="grid gap-5 lg:grid-cols-12">
          <motion.article
            id="workflow"
            initial={{ opacity: 0, y: 28 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.55 }}
            className="feature-spotlight scroll-mt-28 lg:col-span-7 lg:row-span-2"
          >
            <div className="feature-spotlight-glow" />
            <div className="relative z-10 flex h-full flex-col">
              <div className="flex items-start justify-between gap-4">
                <div className="feature-icon">
                  <Search className="h-5 w-5" />
                </div>
                <div className="feature-live-badge">
                  <span /> Live workflow
                </div>
              </div>

              <div className="mt-8 max-w-xl">
                <h3 className="text-2xl font-bold text-foreground sm:text-3xl">
                  Проверка, которая сама ведёт к ответу
                </h3>
                <p className="mt-3 text-base leading-7 text-muted-foreground">
                  Не нужно знать структуру реестров: начните с компании, а сервис сам раскроет важные слои данных.
                </p>
              </div>

              <div className="workflow-track mt-9">
                {steps.map((step, index) => (
                  <div key={step.label} className="workflow-step">
                    <div className="workflow-step-number">0{index + 1}</div>
                    <div className="workflow-step-copy">
                      <strong>{step.label}</strong>
                      <span>{step.value}</span>
                    </div>
                    {index < steps.length - 1 && <ArrowRight className="workflow-arrow" />}
                  </div>
                ))}
              </div>

              <div className="mt-auto pt-9">
                <div className="feature-query">
                  <Search className="h-4 w-4 text-primary" />
                  <span>ООО «ИНФУБЕРИ»</span>
                  <div className="feature-query-status">
                    <Sparkles className="h-3.5 w-3.5" />
                    Досье готово
                  </div>
                </div>
              </div>
            </div>
          </motion.article>

          {capabilities.map((capability, index) => (
            <motion.article
              key={capability.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-70px" }}
              transition={{ duration: 0.45, delay: index * 0.05 }}
              whileHover={{ y: -5 }}
              className="feature-tile lg:col-span-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="feature-icon">
                  <capability.icon className="h-5 w-5" />
                </div>
                <span className="font-mono text-xs text-muted-foreground">{capability.number}</span>
              </div>
              <h3 className="mt-5 text-xl font-bold text-foreground">{capability.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{capability.description}</p>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
};
