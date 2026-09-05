import React from "react";
import { createRoot } from "react-dom/client";
import { Phase4Application } from "./Phase4Application";
import "./styles/application.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Application root is unavailable");
createRoot(root).render(
  <React.StrictMode>
    <Phase4Application />
  </React.StrictMode>
);
