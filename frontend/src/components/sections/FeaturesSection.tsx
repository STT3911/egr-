import { motion } from "framer-motion";
import {
  BarChart3,
  Building2,
  FileText,
  Lock,
  Search,
  Shield,
  Users,
  Zap,
} from "lucide-react";

const features = [
  {
    icon: Search,
    title: "Поиск по УНП",
    description: "Мгновенный поиск по номеру, названию и историческим совпадениям.",
  },
  {
    icon: Building2,
    title: "Карточка компании",
    description: "Статус, адреса, даты, история названий и связанные сведения.",
  },
  {
    icon: FileText,
    title: "Справочники ЕГР",
    description: "Коды, типы, статусы и дополнительные классификаторы в одном месте.",
  },
  {
    icon: BarChart3,
    title: "Быстрая аналитика",
    description: "Работа с данными становится визуально чище и заметно спокойнее.",
  },
  {
    icon: Shield,
    title: "Проверка контрагентов",
    description: "Нужные факты о компании без лишних переходов и перегруженных блоков.",
  },
  {
    icon: Users,
    title: "Работа для команды",
    description: "Интерфейс легко читается и подходит для ежедневной операционной работы.",
  },
  {
    icon: Zap,
    title: "REST API",
    description: "Единая точка доступа для интеграций и внутренних сервисных сценариев.",
  },
  {
    icon: Lock,
    title: "Безопасность",
    description: "Прозрачный доступ к данным с контролем авторизации и стабильной доставкой.",
  },
];

const featured = features[0];
const expanded = features.slice(1, 5);
const secondary = features.slice(5);

const iconBadgeClass =
  "flex h-11 w-11 items-center justify-center rounded-2xl border border-border/80 bg-background/60 text-primary shadow-[inset_0_1px_0_hsl(var(--card)/0.8)]";

export const FeaturesSection = () => {
  return (
    <section id="features" className="relative overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="absolute inset-0 pointer-events-none registry-grid opacity-25" />

      <div className="container relative z-10 mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mb-12 max-w-3xl"
        >
          <div className="eyebrow mb-5">Возможности</div>
          <h2 className="text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
            Визуально спокойный интерфейс для
            <span className="text-gradient"> реальной работы с ЕГР</span>
          </h2>
          <p className="mt-5 text-base leading-7 text-muted-foreground sm:text-lg">
            Вместо пестрых карточек и случайных акцентов теперь все собрано в
            более ровную систему: единые иконки, мягкие поверхности и понятная
            иерархия по важности.
          </p>
        </motion.div>

        <div className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.55 }}
            className="surface-card shadow-card relative overflow-hidden rounded-[2rem] p-7 sm:p-8"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-primary/8 via-transparent to-accent/8" />
            <div className="relative">
              <div className={`${iconBadgeClass} mb-6`}>
                <featured.icon className="h-5 w-5" />
              </div>

              <h3 className="max-w-md text-2xl font-bold text-foreground sm:text-3xl">
                {featured.title}
              </h3>
              <p className="mt-4 max-w-xl text-base leading-7 text-muted-foreground">
                {featured.description}
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                <div className="glass rounded-[1.35rem] p-4">
                  <div className="text-sm font-semibold text-foreground">Автоподсказки</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    Результаты появляются по мере ввода.
                  </div>
                </div>
                <div className="glass rounded-[1.35rem] p-4">
                  <div className="text-sm font-semibold text-foreground">История имен</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    Можно искать не только по текущему названию.
                  </div>
                </div>
                <div className="glass rounded-[1.35rem] p-4">
                  <div className="text-sm font-semibold text-foreground">Быстрый переход</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    Полный УНП сразу открывает профиль компании.
                  </div>
                </div>
              </div>

              <div className="section-divider my-7" />

              <div className="grid gap-3 sm:grid-cols-2">
                {expanded.map((feature) => (
                  <div key={feature.title} className="surface-card rounded-[1.35rem] p-4">
                    <div className="flex items-start gap-3">
                      <div className={iconBadgeClass}>
                        <feature.icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-foreground">{feature.title}</div>
                        <div className="mt-1 text-sm leading-6 text-muted-foreground">
                          {feature.description}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          <div className="grid gap-4">
            {secondary.map((feature, index) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.45, delay: index * 0.05 }}
                whileHover={{ y: -6 }}
                className="surface-card rounded-[1.6rem] p-5 sm:p-6"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className={iconBadgeClass}>
                    <feature.icon className="h-5 w-5" />
                  </div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    0{index + 6}
                  </div>
                </div>

                <h3 className="mt-5 text-lg font-semibold text-foreground">{feature.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {feature.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
