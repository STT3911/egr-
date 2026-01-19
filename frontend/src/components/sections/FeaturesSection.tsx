import { motion } from "framer-motion";
import { 
  Search, 
  Shield, 
  Zap, 
  Users, 
  BarChart3, 
  FileText,
  Building2,
  Lock
} from "lucide-react";

const features = [
  {
    icon: Search,
    title: "Поиск по УНП",
    description: "Мгновенный поиск компании по УНП или названию с автодополнением"
  },
  {
    icon: Building2,
    title: "Профиль компании",
    description: "Полная информация: адрес, статус, дата регистрации, виды деятельности"
  },
  {
    icon: Shield,
    title: "Проверка контрагентов",
    description: "Проверяйте надежность партнеров и контрагентов перед сделками"
  },
  {
    icon: Users,
    title: "Управление командой",
    description: "Приглашайте сотрудников и управляйте доступом к данным"
  },
  {
    icon: BarChart3,
    title: "План закупок",
    description: "Доступ к плану государственных закупок вашей организации"
  },
  {
    icon: FileText,
    title: "Справочники ЕГР",
    description: "Полный набор справочников: статусы, ОПФ, ОКЭД, страны и другие"
  },
  {
    icon: Zap,
    title: "REST API",
    description: "Интеграция через удобный API для автоматизации бизнес-процессов"
  },
  {
    icon: Lock,
    title: "Безопасность",
    description: "JWT аутентификация, шифрование данных, контроль сессий"
  }
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0 }
};

export const FeaturesSection = () => {
  return (
    <section id="features" className="py-20 sm:py-32 bg-background relative">
      <div className="container mx-auto px-4 sm:px-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <span className="inline-block px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium mb-4">
            Возможности
          </span>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold text-foreground mb-4">
            Всё для работы с данными ЕГР
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Полный набор инструментов для поиска, проверки и анализа данных о компаниях Беларуси
          </p>
        </motion.div>

        {/* Features Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6"
        >
          {features.map((feature, index) => (
            <motion.div
              key={index}
              variants={itemVariants}
              className="group p-6 bg-card rounded-2xl border border-border hover:border-primary/30 transition-all duration-300 hover:shadow-card"
            >
              <div className="w-12 h-12 rounded-xl gradient-primary flex items-center justify-center mb-4 group-hover:shadow-glow transition-shadow">
                <feature.icon className="w-6 h-6 text-primary-foreground" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {feature.title}
              </h3>
              <p className="text-muted-foreground text-sm leading-relaxed">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};
