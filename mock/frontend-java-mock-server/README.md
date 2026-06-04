# Frontend Java Mock Server

Tiny throwaway mock server for validating the frontend Java contract over real WebSocket frames.

Run:

```sh
sh backend/gradlew -p mock/frontend-java-mock-server bootRun
```

Run with Docker:

```sh
docker build -t launchpilot/frontend-java-mock:latest mock/frontend-java-mock-server
docker run -d --name launchpilot-frontend-java-mock -p 8090:8090 -e MOCK_PUBLIC_BASE_URL=http://localhost:8090 launchpilot/frontend-java-mock:latest
```

Frontend env:

```sh
NEXT_PUBLIC_AGENT_API_BASE_URL=http://localhost:8090
```

Then run the frontend on port 3000 and inspect `ws://localhost:8090/api/agent/threads/{threadId}/stream` in DevTools.
