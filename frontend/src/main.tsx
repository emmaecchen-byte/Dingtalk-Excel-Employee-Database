import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { LanguageProvider, useLanguage } from "./i18n/LanguageContext";
import { queryClient } from "./lib/queryClient";
import "./index.css";

function AppWithLocale() {
  const { language } = useLanguage();
  return (
    <ConfigProvider locale={language === "zh" ? zhCN : enUS}>
      <AuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <AppWithLocale />
      </LanguageProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
