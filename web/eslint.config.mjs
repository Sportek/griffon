import next from "eslint-config-next";

const config = [...next, { ignores: [".next/**", "node_modules/**", "src/app/vibe.generated.css"] }];

export default config;
