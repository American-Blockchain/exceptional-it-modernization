# Stage 1: Build
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy csproj and restore dependencies
COPY ["Orchestrator.csproj", "./"]
RUN dotnet restore "Orchestrator.csproj"

# Copy full source and publish
# We copy everything in the directory to the build context
COPY . .
RUN dotnet publish "Orchestrator.csproj" -c Release -o /app/publish /p:UseAppHost=false

# Stage 2: Runtime 
# Using the lean ASP.NET Core runtime image
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final
WORKDIR /app
EXPOSE 80
EXPOSE 443

# Copy the published output from the build stage
COPY --from=build /app/publish .

# Configure ASP.NET to listen on port 80 (standard for ACA)
ENV ASPNETCORE_URLS=http://+:80

ENTRYPOINT ["dotnet", "Orchestrator.dll"]
