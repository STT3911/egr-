import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy, useLayoutEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";

const Index = lazy(() => import("./pages/Index"));
const Company = lazy(() => import("./pages/Company"));
const References = lazy(() => import("./pages/References"));
const ReferenceDetail = lazy(() => import("./pages/ReferenceDetail"));
const CompanyRawData = lazy(() => import("./pages/CompanyRawData"));
const CompanyCompare = lazy(() => import("./pages/CompanyCompare"));
const CompanyRelations = lazy(() => import("./pages/CompanyRelations"));
const GiasContract = lazy(() => import("./pages/GiasContract"));
const Admin = lazy(() => import("./pages/Admin"));
const Login = lazy(() => import("./pages/Login"));
const MySubscriptions = lazy(() => import("./pages/MySubscriptions"));
const NotFound = lazy(() => import("./pages/NotFound"));

const queryClient = new QueryClient();

const ScrollToTop = () => {
  const location = useLocation();
  const prevPathnameRef = useRef<string>("");

  useLayoutEffect(() => {
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }

    const pathnameChanged = location.pathname !== prevPathnameRef.current;
    prevPathnameRef.current = location.pathname;

    // Only keep current scroll position when it's a same-page hash navigation
    if (location.hash && !pathnameChanged) {
      return;
    }

    const resetScroll = () => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    };

    resetScroll();
    const frameId = window.requestAnimationFrame(resetScroll);

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [location.pathname, location.hash]);

  return null;
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <ScrollToTop />
        <Suspense fallback={<div className="min-h-screen bg-background" />}>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/company/:unp" element={<Company />} />
            <Route path="/company/:unp/raw" element={<CompanyRawData />} />
            <Route path="/company/:unp/compare" element={<CompanyCompare />} />
            <Route path="/company/:unp/relations" element={<CompanyRelations />} />
            <Route path="/contracts/:contractId" element={<GiasContract />} />
            <Route path="/references" element={<References />} />
            <Route path="/references/:type" element={<ReferenceDetail />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/login" element={<Login />} />
            <Route path="/subscriptions" element={<MySubscriptions />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
